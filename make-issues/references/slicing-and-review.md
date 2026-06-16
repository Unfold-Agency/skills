# Slicing & Review (Generate / new items)

How to turn an approved, version-locked TDD into a set of thin GitHub work items. The prime directive: **slice for an agent's single loop, then review before you write.** A work item that an agent can build, test, verify, and merge in one pass is worth ten that need a meeting to start. Nothing reaches GitHub before the human approves the breakdown.

## 1. Read both sources, in order

The preflight gate has already confirmed the version lock (`prd-data.meta.prd_version == tdd-data.meta.prd_version`); if it had not, you would not be here. Now read for content:

1. **`tdd-data.yaml`** -- the capabilities you will slice: entities (`ENT-`), workflows (`WF-`), state machines (`STM-`), integrations (`INTG-`), NFRs (`TNF-`), and decisions (`ADR-`). Also `traceability.mapped` (which PRD requirement each capability satisfies) and the binding constraints (`BC-`) the work must respect.
2. **`prd-data.yaml`** -- the objectives and success criteria each capability ultimately serves. The issue's *Goal* and *Success criteria* come from here, in the user's terms.
3. The TDD Markdown when a capability's prose matters (a sequence diagram, an error path). Reference it by section/ID in the issue; **do not copy it** -- the TDD stays canonical.

Skip capabilities whose `status` is `superseded` or `deferred` -- they are not work. Slice only `active` ones.

## 2. Cut thin slices

A work item is a thin, independently-completable vertical slice -- not an epic, not a layer. Structure comes from dependencies and trace labels, not a hierarchy (see SKILL.md). Apply these tests:

- **End-to-end and verifiable alone.** Each item can be built, tested, and merged without waiting on a sibling to be half-done. If proving it done requires another unfinished item, fold them or order them with a dependency.
- **Prefer many thin to few thick.** A capability usually becomes several items (the data model; one workflow path; the failure branch; the integration contract; the NFR's test). Splitting along the TDD's own seams -- one `WF-` path, one `INTG-` contract -- keeps each item traceable.
- **One capability can fan out; one item should not span unrelated capabilities.** Keep the trace clean: an item that satisfies `WF-003` and nothing else is easy to reconcile later.

## 3. Mark autonomy: AFK or HITL

Every item carries one autonomy flag -- the signal the overnight loop reads to decide what it can own unattended. **Prefer AFK.** Mark `hitl` only when a human genuinely must be in the loop:

- **AFK** -- the success criteria are checkable by tests/lint/build; the slice has no irreversible side effect and no judgment call an agent can't make from the TDD.
- **HITL** -- the item needs a human decision (a visual/brand judgment, a security or data-migration sign-off, anything that touches production data or money, or a back-out of shipped work).

When unsure, ask what would happen if an agent finished it at 3am with no one watching. If that's fine, it's AFK.

## 4. Assemble each item's fields

Fill the template (`assets/issue-body-template.md`) from the two sources:

| Field | Source |
|---|---|
| Goal | the PRD objective the capability serves |
| What to build | the TDD capability (reference its ID/section) |
| Success criteria | the PRD success criteria, in the user's terms |
| Acceptance criteria | checkable items; last box is always the build gate |
| Test plan | the TDD (unit / integration / e2e / a11y / perf as applicable) |
| `trace_tdd` | the capability ID(s) this item satisfies |
| `trace_prd` | the PRD requirement IDs those transitively trace to (via `traceability`) |
| `source_versions` | the locked PRD + TDD versions from the two `meta` blocks |
| `fingerprint` | `scripts/item_fingerprint.py <tdd-data.yaml> --id <CAP>` |
| `autonomy` | AFK or HITL, from step 3 |

**No item without a trace.** Every issue stamps at least one `trace_tdd` capability and the PRD IDs it serves. An item you cannot trace to the TDD is an item the TDD does not justify -- cut it or fix the TDD.

## 5. Order the dependencies as a DAG

Express what-blocks-what as native GitHub dependencies (`--blocked-by`), not a parent/child tree. Derive the edges from the TDD: a workflow that reads an entity is blocked by the entity's item; an integration the workflow calls blocks the workflow. Before presenting, **check the graph is acyclic** -- a cycle means two items each wait on the other and neither can start. Report any cycle as a path (`A -> B -> A`) and break it (usually by merging or re-slicing) rather than shipping contradictory links.

## 6. The review pass -- the human gate

Before creating or changing **anything**, present the breakdown and get approval. This is the gate, the same recommend-then-refine the PRD and TDD use. Show:

- A numbered list of work items. For each: **title · AFK/HITL · blocked-by · trace IDs**.
- The **coverage check**: every `active` capability has at least one item, or the gap is named. Every PRD `must`/`should` requirement traces through to an item, or it is listed as unmapped.
- For a sync, the **reconciliation plan**: what will be created, updated, flagged, closed, or followed-up (see `reconciliation.md`).

Iterate until the human approves. Only then create issues -- in dependency order, blockers first, so each `--blocked-by` references an issue number that already exists. Stamp every issue per the template and apply its labels (`make-issues`, `afk`/`hitl`, one `trace:<ID>` per traced ID, `src:prd-<v>`, `src:tdd-<v>`).
