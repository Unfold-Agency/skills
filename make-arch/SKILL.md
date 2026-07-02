---
name: make-arch
description: Propose and maintain the architecture layer of a project spec -- a thin C4/arc42-lite architecture overview with mermaid diagrams, plus an append-only Architecture Decision Record (ADR) log. Use this skill after make-spec, whenever the user wants to choose or change the tech stack, decide an integration or data approach, record "which database / payment processor / framework are we using and why", add or supersede an ADR, or draw the system's architecture diagrams. Trigger it for "what's our architecture", "pick the stack", "write an ADR", "we're switching from X to Y", or "diagram the system". This is the HOW layer; the WHAT (features, requirements) is the upstream make-spec skill. Do NOT use it to author feature requirements.
---

# Make Architecture

Produce and maintain the **architecture layer** that sits under a `make-spec` spec
set: how the system is built, and the decisions behind it. Two artifacts, both in
`docs/product/`:

```
docs/product/
  architecture.md / arch-data.yaml      # a thin C4/arc42-lite overview: context,
                                          #   components, integrations + MERMAID
  decisions/ADR-NNNN-<slug>.md           # an APPEND-ONLY ADR log, one file per
                                          #   decision (Status/Context/Decision/
                                          #   Consequences + rejected alternatives)
```

This is the chosen replacement for a monolithic TDD. The win: a **decision** like
"which payment processor" lives in one immutable ADR, findable in ≤ 2 hops from any
feature (feature requirement -> its `governed_by` ADR), and it stays in sync because
you never edit an accepted decision -- you supersede it.

**The doctrine: architecture serves the features.** make-arch reads the
`make-spec` overview + every feature spec and proposes the stack that covers them.
It decides HOW; it never edits the WHAT (run `/make-spec` for that).

## When to skip it

`--lite` projects (a brochure site, a one-feature tool) declared in the overview do
**not** need this layer until a real architectural decision arises. `make-spec
--lite` produces overview + features only; reach for `make-arch` the first time a
genuine HOW decision shows up.

## Modes

- **Kickoff** (no architecture yet) -- read the overview + features, recommend the
  stack, write `architecture.md` + the first ADRs. Read
  `references/recommend-then-refine.md`.
- **Amend** (architecture exists) -- add a component/integration, or **add a new
  ADR**. Changing a decision is a *new superseding ADR*, never an edit to the old
  one. Read `references/adr-protocol.md`.

## The two disciplines this skill protects

- **Recommend-then-refine, with confidence as typed data.** Propose a concrete
  stack -- don't hedge into a menu -- but type every choice: `known` (backed by a
  stated requirement/constraint/client fact -- cite it) or `assumption` (a sensible
  default pending confirmation). Assumption-backed choices get a visible badge in
  `architecture.md`, so a human refines against exactly the unconfirmed calls. See
  `references/recommend-then-refine.md`.
- **Append-only ADRs.** One decision per file; numbered in order; never edited once
  accepted; reversed only by a superseding ADR (the old one stays, marked
  `Superseded by`). See `references/adr-protocol.md`.

## Files in this skill

- `assets/architecture-template.md` -- the architecture overview template (with the
  required mermaid context diagram). HTML comments are authoring guidance; strip them.
- `assets/adr-template.md` -- the Nygard ADR template (Status/Context/Decision/
  Consequences/rejected alternatives).
- `assets/arch-data-schema.yaml` -- the schema for `arch-data.yaml`, the fingerprint
  IN/OUT contract, and validator rules A-001..A-008. Read before deriving the YAML.
- `references/recommend-then-refine.md` -- proposing a stack and typing confidence.
- `references/adr-protocol.md` -- the append-only ADR rules and the supersede flow.
- `references/diagrams.md` -- the mermaid diagram kinds (context/container/sequence/ERD).
- `scripts/stamp_fingerprint.py` -- stamps `arch-data.yaml`'s fingerprint + version.
- `scripts/validate_arch.py` -- run after every stamp. Never present an architecture
  whose data file fails validation.

## The derive -> stamp -> validate loop

1. Author/edit `architecture.md` and the ADR file(s) (the template comments are the
   rules; keep the overview thin -- the durable detail is in the ADRs).
2. Derive `arch-data.yaml` per the schema (the ADR index, components, integrations,
   diagrams, and each choice's confidence).
3. `python scripts/stamp_fingerprint.py docs/product`
4. `python scripts/validate_arch.py docs/product` (add `--no-baseline` only on the
   greenfield first commit, before `main` carries the docs). The validator enforces
   ADR format + supersede discipline, no-orphan (every accepted feature-scoped ADR
   is referenced by a feature), typed confidence, a present mermaid context diagram,
   a **fail-closed fingerprint gate**, and the **append-only `origin/main`
   baseline** (an ADR that existed there may never vanish). Fix every failure.

## How a decision changes (the common asks)

- **Choose something** (Stripe, Postgres) -> a new `ADR-NNNN` (Accepted, + rejected
  alternatives), update `architecture.md`/diagram, link it from the governing
  feature requirement's `governed_by`. Record it in the spec `CHANGELOG.md`.
- **Reverse a decision** -> a NEW ADR marking the old one `Superseded`; never edit
  the old file. Downstream, `/make-issues` opens refactor issues for merged work the
  reversal invalidated.
- **Lower-confidence call** -> record it as an `assumption` ADR (reversible by
  design) and badge it, rather than inventing a constraint to make it look `known`.

## Honest limits

Be honest about what the gate proves: the fingerprint certifies that
`arch-data.yaml` has not changed since it was stamped -- nothing more. It does
not prove the decisions are implemented (an accepted ADR may be half-built or
quietly diverged from in code -- the issue roll-up in make-trace is the closer
signal), that a human re-read the file before re-stamping, or who authored a
change (git carries authorship). `architecture.md` is a human-written narrative:
its value is the synthesis a newcomer builds a mental model from, so keep it
prose-first and let the ADRs carry the durable detail -- never generate the
narrative from the data file.

## Downstream

`/make-issues` reads the features + this ADR index and stamps each issue with
`trace_adr` (its governing decision); `/do-work` builds from those issues. Change
flows forward: add/supersede an ADR here -> re-run `/make-issues` to reconcile.

Optionally, once the architecture is settled, `/make-data-flows` embeds per-feature
data-flow and user-flow diagrams (Mermaid) into the feature specs, and
`/make-api-contracts` derives a mock-ready OpenAPI contract from them (referencing this
layer's integrations/ADRs by id via `x-integration` / `x-trace-adr`, never redefining an
external provider). Both are **advisory** -- they never gate the build.

## Writing rules

Plain words, short sentences, no marketing language. One decision per ADR. Never use
an em dash; use a spaced double hyphen ` -- ` for asides. Be honest about trade-offs
and about which choices are still assumptions.
