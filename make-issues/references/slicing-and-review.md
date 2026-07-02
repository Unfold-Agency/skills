# Slicing & Review (new items)

How to turn the selected slice of a spec set into thin GitHub work items. The prime directive: **slice for an agent's single loop, then review before you write.** A work item that an agent can build, test, verify, and merge in one pass is worth ten that need a meeting to start. Nothing reaches GitHub before the human approves the breakdown.

This covers the **selected scope** only -- the feature(s)/requirement(s) (or the amendment) the run is scoped to; see `references/scoping-and-modes.md` for how a run is scoped and for the spec-set precondition. Two kinds of item are cut here: a **spec** item (projects a requirement -- most of this reference) and an **amendment** item (added on demand, authored against a feature anchor -- see step 4b). Detection is global but you only slice/create within scope.

## 1. Read the specs, in order

The preflight gate has already run the scoped fingerprint gate: every **selected** feature's stored `meta.fingerprint` equals a recompute over its CONTRACT content (a dirty selected feature would have failed the gate; a dirty unselected or project file only warned, since this run will not build from it). So the specs you are about to slice are clean. Now read for content:

1. **`features/<slug>.md`** -- the `requirements` you will slice. **The requirement is the work item.** Each carries `id` (e.g. `FR-CHK-001`), `name`, `kind`, `description`, EARS `acceptance_criteria` (order-significant), `verification` (schema 1.1+: the `{method, check, covers}` proof plan), `governed_by` (ADR ids), `depends_on` (requirement ids, may cross features), `interface`, advisory fields, and `status`.
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
- the **verification entries** (`verification`, schema 1.1+) -- the proof plan the builder executes and cites as as-built evidence (`## Verification` section; omit only for a 1.0 requirement that predates the field);
- the **interface** (`interface`), if any;
- a **one-line snippet of each governing ADR** (id, title, decision), from `arch-data.yaml`, with a back-link to its `decisions/ADR-NNNN-*.md` file.

The specs stay canonical -- reference the requirement and ADR ids; do not paraphrase scope. To change scope you change the feature spec and re-sync.

## 4. Mark autonomy: AFK or HITL

Every item carries one autonomy flag -- the signal the overnight loop reads to decide what it can own unattended. **Prefer AFK.** Mark `hitl` only when a human genuinely must be in the loop:

- **AFK** -- the acceptance criteria are checkable by tests/lint/build; the slice has no irreversible side effect and no judgment call an agent can't make from the requirement.
- **HITL** -- the item needs a human decision (a visual/brand judgment, a security or data-migration sign-off, anything that touches production data or money, or a back-out of shipped work -- every REFACTOR is HITL).

**The verification methods are the machine-provability signal.** When the
requirement carries `verification` (schema 1.1+), read the methods: `test` /
`analysis` / `monitor` entries are proofs an unattended worker can run or cite,
while `demo` / `inspection` entries are human-judgment proofs it cannot claim.
An item whose criteria are provable **only** by demo/inspection defaults to
**HITL** -- an AFK worker would just build it and park it `deferred` at the
acceptance gate, so mark the human in from the start. A mixed plan can stay AFK;
the worker meets what it can prove and honestly defers the judgment rows.

When unsure, ask what would happen if an agent finished it at 3am with no one watching. If that's fine, it's AFK.

**AFK REQUIRES CHECKABLE ACCEPTANCE CRITERIA.** An item with no acceptance criteria a build could verify against cannot be AFK -- there is nothing to prove it done. Spec items always embed the requirement's EARS criteria, so this is automatic; an **amendment** must have criteria you authored, or it must be `hitl`. `do-work` enforces this too: it refuses to auto-build an issue with no `## Acceptance criteria` checklist, whatever the label says. Do not mark an item AFK to move it faster -- write the criteria, or mark it HITL.

### 4b. Authoring an amendment item

An amendment is on-demand work not (yet) a requirement, still anchored to the spec set (a "quick amendment, not a rewrite"). When the run is authoring one (see `references/scoping-and-modes.md` for the description disambiguation that decides select-vs-author):

- Anchor it: name the real `feature` slug it belongs to (required), plus any goal it serves and governing ADRs.
- **Author** the Goal, Requirement, and Acceptance criteria yourself -- there is no spec to embed from. Make the criteria checkable.
- Set `provenance: amendment`, `trace_req: []` (or the requirement you intend to promote to), `fingerprint: ""`, `source_version: ""`; apply the `amendment` label.
- Autonomy per the rule above: AFK only with authored checkable criteria, else HITL.

Everything downstream (dependencies, the review gate, creation order) is the same as a spec item.

## 5. Assemble each item's fields

Fill the template (`assets/issue-body-template.md`) from the specs:

| Field | Source |
|---|---|
| Goal | the overview `goal` (G-NNN) the feature serves |
| Requirement | the requirement `description`, embedded verbatim (reference its id) |
| Acceptance criteria | the requirement `acceptance_criteria`, embedded verbatim and in order; last box is always the build gate |
| Verification | the requirement `verification` entries (schema 1.1+), embedded as `method (covers) -- check` lines; omit for a 1.0 requirement |
| Interface | the requirement `interface`, if any |
| Governing decisions | one line per `governed_by` ADR (id, title, decision snippet) from `arch-data.yaml`, with a back-link |
| `trace_req` | the requirement id this item satisfies (>=1, required) |
| `trace_adr` | the requirement's `governed_by` ADR ids (may be empty) |
| `feature` | the feature slug the requirement lives in |
| `source_version` | the feature's `feature_version` from its `meta` block |
| `fingerprint` | `scripts/item_fingerprint.py docs/product --id <REQ>` |
| `autonomy` | AFK or HITL, from step 4 |
| `## Traceability` table | one row per `trace_req` / `trace_adr` ID with its title from the source spec, plus a feature row; close with "Born from feature <slug> v<feature_version>". The human-readable mirror of the trace fields -- it replaces the old per-ID `trace:` labels |

**No item without a trace.** Every issue traces back to the spec set. A **spec** item stamps at least one `trace_req` requirement -- that is its required trace; an empty `trace_req` is not allowed for a spec item. An **amendment** item may have an empty `trace_req` but must name a real `feature` **anchor** (that is its trace). `trace_adr` lists the governing ADRs and may be empty either way. A spec item you cannot trace to a requirement is one the specs do not justify -- cut it, fix the feature spec, or make it an amendment anchored to the right feature.

**Place each item in its phase (when the overview has a plan).** Phasing is OPTIONAL. If `overview.md` declares a `phasing` list, every issue rolls up to the phase its **feature** belongs to -- the grouping `do-work --phase=N` drains. Get the mapping once: `python scripts/phase_milestones.py docs/product/overview.md --json` returns `feature_to_phase` (slug -> phase number) and `phase_title` (number -> milestone title `Phase <N>: <name>`). An item's phase is the phase of its `feature`. Phase is **sequencing, not contract** -- it is carried by the GitHub **milestone**, never written into the issue body or meta block, so re-phasing later never churns the fingerprint. An overview with no `phasing` plan skips milestones entirely; nothing else about slicing changes.

## 6. Order the dependencies as a DAG

Express what-blocks-what as native GitHub dependencies (`--blocked-by`), not a parent/child tree. Derive the edges from the requirements' own `depends_on` lists (requirement ids, which may cross features): an item is blocked by the items of the requirements it depends on. Mirror the edges in the issue body's `## Dependencies` section (the verifiable record -- native edges cannot be read back). Before presenting, **check the graph is acyclic** -- a cycle means two items each wait on the other and neither can start. Report any cycle as a path (`A -> B -> A`) and break it (usually by merging or re-slicing) rather than shipping contradictory links.

## 7. Run analyze, then the review pass -- the human gate

Before creating or changing **anything**, run the planner and present the breakdown. Pass the run's `--scope` so writes are bounded to the selected slice (detection stays global):

```
python scripts/analyze.py --spec-dir docs/product --issues <gh-json> --scope <tokens>
```

With no existing issues the plan is a clean all-CREATE within scope; on a re-run it must exit 0 (or a human approves its remediation report) before any write -- it is the hard gate. Then show:

- The work items, **grouped by phase** when the overview has a plan (a phase header per `Phase N: name`, its items beneath). For each item: **title · AFK/HITL · blocked-by · trace IDs**.
- The **coverage check**, honest about scope: every in-scope `active` requirement has at least one item, or the gap is named. On a scoped run say **PARTIAL** -- name the in-scope features and note how many requirements elsewhere were not acted on. Every in-scope overview `goal` traces through to an item, or it is listed as unmapped. With a plan, also: every active in-scope phase has at least one item and any phase-spanning feature is flagged.
- The **out-of-scope drift** from `plan["out_of_scope"]`: drift the global census found outside the scope, detected but not written. Show it so the operator knows what a wider run would touch.
- The **reconciliation plan** from analyze: what will be created, updated, flagged, closed, refactored, or promoted within scope (see `reconciliation.md`), plus any milestone re-assignments and the watermark window.

Iterate until the human approves. Then, when the overview has a plan, **ensure the milestones exist first** -- `python scripts/phase_milestones.py docs/product/overview.md --ensure --repo <owner/name>` creates one milestone per phase (idempotent). Now create issues -- in dependency order, blockers first, so each `--blocked-by` references an issue number that already exists. Stamp every issue per the template, apply its labels (`make-issues` and `afk`/`hitl`, plus `amendment` for an amendment item), and assign its phase milestone: `gh issue create ... --milestone "Phase <N>: <name>"`. Traceability and source version are carried in the body (`## Traceability` table) and the meta block; the phase is carried by the milestone -- neither is a label. After the create run, **write the watermark** (`docs/product/.make-issues-sync.json`) at each feature's current `feature_version` and commit it (see reconciliation.md §2).
