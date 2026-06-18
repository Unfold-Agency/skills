<!--
  ISSUE BODY TEMPLATE — make-issues
  The body is a sandwich of named regions on HTML comment markers.

  Auto-sync (reconciliation) patches ONLY the managed regions:
    - the prose above the meta marker (Goal .. Dependencies)
    - the make-issues:meta block
    - the make-issues:changelog block
  Auto-sync NEVER touches the make-issues:human block. The reconciler splices
  that block back byte-for-byte and refuses to write if it cannot (see
  references/reconciliation.md, "Managed-region surgery").

  Fill the angle-bracket placeholders, strip these authoring comments, then
  create the issue. One work item = one issue = one thin, end-to-end slice.
-->

## Goal

<!-- The PRD objective this work item serves. One or two plain sentences. Trace it below. -->

## What to build

<!-- The end-to-end slice, sourced from the TDD capability. Reference the TDD
     section/ID (e.g. "per WF-003"); do not duplicate the design here -- the TDD
     stays canonical. State what "done" looks like at the seam. -->

## Success criteria

<!-- From the PRD success criteria for the objective above. What the business
     needs to be true, in the user's terms. -->

## Acceptance criteria

<!-- Checkable, agent-actionable. The last box is always the build gate. -->
- [ ] <criterion 1>
- [ ] <criterion 2>
- [ ] Typecheck / lint / tests pass

## Test plan

<!-- From the TDD: unit / integration / e2e / a11y / perf as applicable to this
     slice. Enough that an agent knows how to prove the work. -->

## Dependencies

<!-- Human-readable mirror of the native blocked-by links. List the issue
     numbers/titles this waits on, or "None". The authoritative edges are the
     GitHub dependency links set with `gh issue create --blocked-by`. -->

## Traceability

<!-- Human-readable mirror of the trace_tdd / trace_prd / source_versions in the
     meta block below (which is the machine-authoritative copy). One row per
     traced ID, with its title pulled from the TDD/PRD so a reader knows what it
     is without opening the source doc. This replaces the old per-ID `trace:`
     labels -- it is synced like any other managed region. -->

| Source | ID | What it is |
|---|---|---|
| TDD capability | <CAP-000> | <capability title from the TDD> |
| PRD requirement | <UO-000> | <requirement title from the PRD> |

Born from PRD v<X> / TDD v<Y>.

<!-- make-issues:meta -->
```yaml
trace_tdd: [CAP-000]               # TDD capability IDs this issue satisfies (ENT/WF/STM/INTG/TNF/ADR)
trace_prd: [UO-000]                # PRD IDs the capability links to (its satisfies / PRD-side derived_from); may be empty
source_versions: { prd: "0.0", tdd: "0.0" }   # the locked PRD + TDD versions this was born from
autonomy: afk                      # afk | hitl  -- can the overnight loop own this unattended?
fingerprint: "<item-hash>"         # per-capability hash from scripts/item_fingerprint.py
```
<!-- /make-issues:meta -->

<!-- make-issues:changelog -->
## Change log
- <YYYY-MM-DD> -- created from PRD v<X> / TDD v<Y>
<!-- /make-issues:changelog -->

<!-- make-issues:human -->
## Notes (human-maintained -- never overwritten by sync)

<!-- Engineers may add context, extra success criteria, gotchas, or constraints
     here. This region is preserved verbatim across every sync. It does NOT
     trickle up to the PRD/TDD -- to change scope, change the TDD and re-sync. -->
<!-- /make-issues:human -->
