<!--
  ISSUE BODY TEMPLATE -- make-issues
  The body is a sandwich of named regions on HTML comment markers.

  Auto-sync (reconciliation) patches ONLY the managed regions:
    - the prose above the meta marker (Goal .. Dependencies)
    - the make-issues:meta block
    - the make-issues:changelog block
  Auto-sync NEVER touches the make-issues:human block. The reconciler splices
  that block back byte-for-byte and refuses to write if it cannot (see
  references/reconciliation.md, "Managed-region surgery").

  An issue is a self-contained vertical slice. Embed everything a builder needs
  to act WITHOUT opening the specs: the requirement text, its EARS acceptance
  criteria, its verification entries (the proof plan), a one-line snippet of
  each governing ADR, and back-links. The specs stay canonical -- to change
  scope you change the feature spec and re-sync, you never edit the requirement
  here.

  Fill the angle-bracket placeholders, strip these authoring comments, then
  create the issue. One work item = one issue = one thin, end-to-end slice.
-->

## Goal

<!-- The product goal this slice serves, in plain terms. Sourced from the
     overview goal (G-NNN) the feature rolls up to. One or two sentences. -->

## Requirement

<!-- The requirement text, embedded verbatim from the feature spec's
     `description` (req id below). A builder should not need to open the spec.
     Reference the feature + requirement id (e.g. "FR-CHK-001 in feature
     checkout"); the spec stays canonical. -->

> <requirement description, embedded>

## Acceptance criteria

<!-- The requirement's EARS `acceptance_criteria`, embedded verbatim and IN
     ORDER (order is part of the contract), as checkable boxes. The last box is
     always the build gate. -->
- [ ] <EARS criterion 1, embedded from the requirement>
- [ ] <EARS criterion 2, embedded from the requirement>
- [ ] Typecheck / lint / tests pass

## Verification

<!-- The requirement's `verification` entries (schema 1.1+), embedded from the
     feature spec: HOW the criteria above will be PROVEN. The builder executes
     the machine-runnable entries (test / analysis / monitor) and cites them as
     as-built evidence; a demo / inspection entry is a human-judgment proof an
     unattended worker cannot claim as met -- it records the steps and defers.
     Omit the section only when the source requirement predates verification
     (schema 1.0); the criteria above are then the only acceptance surface. -->
- `test` (negative) -- <check, embedded from the requirement>
- `test` (positive) -- <check, embedded from the requirement>

## Interface

<!-- The requirement's `interface` (data shape / signature), if any, embedded so
     the builder knows the seam. Omit the section if the requirement has none. -->

## Governing decisions

<!-- One line per governing ADR (from the requirement's `governed_by`): its id,
     title, and a one-line snippet of the decision, plus a back-link to the ADR
     file. So the builder knows the constraint without opening the arch spec. -->
- <ADR-NNNN> -- <title>: <one-line decision snippet>  (see `docs/product/decisions/<ADR-NNNN>-*.md`)

## Dependencies

<!-- Human-readable mirror of the native blocked-by links, derived from the
     requirement's `depends_on` (requirement ids, which may cross features). List
     the issue numbers/titles this waits on, or "None". The authoritative edges
     are the GitHub dependency links set with `gh issue create --blocked-by`. -->

## Traceability

<!-- Human-readable mirror of the trace_req / trace_adr / feature / source_version
     in the meta block below (which is the machine-authoritative copy). One row
     per traced ID, with its title so a reader knows what it is without opening
     the source spec. Synced like any other managed region. -->

| Source | ID | What it is |
|---|---|---|
| Requirement | <FR-XXX-000> | <requirement name from the feature spec> |
| Governing ADR | <ADR-0000> | <ADR title from arch-data.yaml> |
| Feature | <slug> | <feature title from the feature_index> |

Born from feature <slug> v<feature_version>.

<!-- make-issues:meta -->
```yaml
provenance: spec                   # spec | amendment (absent == spec). See the amendment note below.
trace_req: [FR-XXX-000]            # requirement id(s) this issue satisfies (^(FR|IR|NFR|CR)-[A-Z]{2,5}-\d{3,}$); spec: >=1 required; amendment: may be []
trace_adr: [ADR-0000]              # governing ADR ids, from the requirement's governed_by; may be empty
feature: <slug>                    # the feature slug this requirement/anchor lives in (REQUIRED -- it is the amendment anchor)
source_version: "0.0"              # the feature_version this issue was born from ("" for an amendment)
autonomy: afk                      # afk | hitl  -- afk REQUIRES acceptance criteria; can the overnight loop own this unattended?
fingerprint: "<item-hash>"         # per-requirement hash from scripts/item_fingerprint.py ("" for an amendment -- no requirement to hash)
```
<!-- /make-issues:meta -->

<!--
  AMENDMENT VARIANT (provenance: amendment)
  An amendment is a "quick amendment, not a rewrite": work added on demand that is
  not (yet) a requirement in the specs, but still anchored to the existing spec set.
  make-issues never runs without a spec set, so an amendment always references real
  features/goals/ADRs -- it is scoped and traceable, not a willy-nilly ticket.
  For an amendment:
    - set `provenance: amendment` and apply the `amendment` label;
    - `feature` is the REQUIRED anchor (a real feature slug from the feature_index);
      trace_adr / a goal may also anchor it; trace_req may be [] (or list the
      requirement it will PROMOTE to, once one exists);
    - leave `fingerprint: ""` and `source_version: ""` -- there is no requirement hash;
    - AUTHOR the Requirement + Acceptance criteria yourself (they are not embedded from
      a spec). afk REQUIRES checkable acceptance criteria; an amendment with none must
      be `hitl` -- do-work refuses to auto-build a criteria-less issue.
  Reconciliation leaves an amendment's body alone (it is human-owned, like the human
  region), never orphan-closes or refactors it, and only flags it if its feature
  anchor disappears. When a real requirement later covers it, PROMOTE it (see
  references/reconciliation.md): trace_req is set, provenance flips to spec, and the
  fingerprint is stamped -- in place, no duplicate.
-->


<!-- make-issues:changelog -->
## Change log
- <YYYY-MM-DD> -- created from feature <slug> v<feature_version>
<!-- /make-issues:changelog -->

<!-- make-issues:human -->
## Notes (human-maintained -- never overwritten by sync)

<!-- Engineers may add context, extra success criteria, gotchas, or constraints
     here. This region is preserved verbatim across every sync. It does NOT
     trickle up to the specs -- to change scope, change the feature spec and
     re-sync. -->
<!-- /make-issues:human -->
