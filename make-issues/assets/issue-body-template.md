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
  criteria, a one-line snippet of each governing ADR, and back-links. The specs
  stay canonical -- to change scope you change the feature spec and re-sync, you
  never edit the requirement here.

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

## Interface

<!-- The requirement's `interface` (data shape / signature), if any, embedded so
     the builder knows the seam. Omit the section if the requirement has none. -->

## Governing decisions

<!-- One line per governing ADR (from the requirement's `governed_by`): its id,
     title, and a one-line snippet of the decision, plus a back-link to the ADR
     file. So the builder knows the constraint without opening the arch spec. -->
- <ADR-NNNN> -- <title>: <one-line decision snippet>  (see `docs/specs/decisions/<ADR-NNNN>-*.md`)

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
trace_req: [FR-XXX-000]            # requirement id(s) this issue satisfies (^(FR|IR|NFR|CR)-[A-Z]{2,5}-\d{3,}$); >=1, required
trace_adr: [ADR-0000]              # governing ADR ids, from the requirement's governed_by; may be empty
feature: <slug>                    # the feature slug this requirement lives in
source_version: "0.0"              # the feature_version this issue was born from
autonomy: afk                      # afk | hitl  -- can the overnight loop own this unattended?
fingerprint: "<item-hash>"         # per-requirement hash from scripts/item_fingerprint.py
```
<!-- /make-issues:meta -->

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
