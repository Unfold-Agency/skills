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
  architecture.md               # a thin C4/arc42-lite overview: the FRONTMATTER
                                #   carries the machine contract (context,
                                #   components, integrations, diagrams); the body
                                #   is the human narrative + MERMAID
  decisions/ADR-NNNN-<slug>.md  # an APPEND-ONLY ADR log, one file per decision;
                                #   each file's FRONTMATTER is its machine record
                                #   (id/title/status/scope/confidence/...), the
                                #   body its Nygard prose (Context/Decision/
                                #   Consequences + rejected alternatives)
```

**One file per document -- there is no derived `arch-data.yaml`.** The bytes a
human reviews and signs ARE the bytes the pipeline validates and consumes
(make-issues snippets, make-trace, make-api-contracts all read the frontmatter).
This closes the same fidelity gap the single-file spec design closed for
make-spec: previously the gate hashed an LLM-derived YAML copy the human never
signed. A project still carrying `arch-data.yaml` migrates in one command --
`python scripts/migrate_arch_data.py docs/product`.

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
  superseded). The validator enforces this mechanically against `origin/main`: an
  accepted ADR's bytes may change ONLY by the supersede transition -- frontmatter
  `status` -> `superseded`/`deprecated` plus `superseded_by` -- and any other edit
  fails A-009. See `references/adr-protocol.md`.

## Files in this skill

- `assets/architecture-template.md` -- the architecture overview template (with the
  required mermaid context diagram). HTML comments are authoring guidance; strip them.
- `assets/adr-template.md` -- the Nygard ADR template (Status/Context/Decision/
  Consequences/rejected alternatives).
- `assets/arch-schema.yaml` -- both frontmatter shapes (architecture.md + ADR), the
  fingerprint IN/OUT contract, and validator rules A-001..A-009. Read before
  authoring the layer.
- `references/recommend-then-refine.md` -- proposing a stack and typing confidence.
- `references/adr-protocol.md` -- the append-only ADR rules and the supersede flow.
- `references/diagrams.md` -- the mermaid diagram kinds (context/container/sequence/ERD).
- `scripts/stamp_fingerprint.py` -- stamps `architecture.md`'s frontmatter
  fingerprint + version (the body is preserved; ADR files are never stamped --
  their regime is append-only, gated against the git baseline).
- `scripts/validate_arch.py` -- run after every stamp. Never present an architecture
  that fails validation.
- `scripts/migrate_arch_data.py` -- the one-time v1.0 -> v2.0 migration: injects
  each ADR's frontmatter from the legacy index, moves the contract into
  `architecture.md`'s frontmatter, deletes `arch-data.yaml`, re-stamps.

## The author -> stamp -> validate loop

1. Author/edit `architecture.md` -- the structured contract in the **frontmatter**
   (context, components, integrations, diagrams, per the schema), the narrative +
   mermaid in the body -- and the ADR file(s), each with its frontmatter record and
   Nygard prose (the template comments are the rules; keep the overview thin -- the
   durable detail is in the ADRs). There is no separate data file to derive.
2. `python scripts/stamp_fingerprint.py docs/product`
3. `python scripts/validate_arch.py docs/product` (add `--no-baseline` only on the
   greenfield first commit, before `main` carries the docs). The validator enforces
   ADR format + supersede discipline, no-orphan (every accepted feature-scoped ADR
   is referenced by a feature), typed confidence, a present mermaid context diagram,
   a **fail-closed fingerprint gate** on `architecture.md`, the **append-only
   `origin/main` baseline** (an ADR that existed there may never vanish, A-008),
   and **immutability once accepted** (an accepted ADR's bytes may change only by
   the supersede transition, A-009). Fix every failure.

## How a decision changes (the common asks)

- **Choose something** (Stripe, Postgres) -> a new `ADR-NNNN` (Accepted, + rejected
  alternatives), update `architecture.md`/diagram, link it from the governing
  feature requirement's `governed_by`. Record it in the spec `CHANGELOG.md`.
- **Reverse a decision** -> a NEW ADR, then apply the supersede transition to the
  old file's frontmatter (`status: superseded`, `superseded_by: ADR-MMMM`) -- the
  one edit A-009 allows; its prose is never touched. Downstream, `/make-issues`
  opens refactor issues for merged work the reversal invalidated.
- **Lower-confidence call** -> record it as an `assumption` ADR (reversible by
  design) and badge it, rather than inventing a constraint to make it look `known`.

## Honest limits

Be honest about what the gates prove: the fingerprint certifies that
`architecture.md`'s frontmatter has not changed since it was stamped, and the
baseline gates (A-008/A-009) certify the ADR log only grew and no accepted
decision was edited -- nothing more. They do not prove the decisions are
implemented (an accepted ADR may be half-built or quietly diverged from in code
-- the issue roll-up in make-trace is the closer signal), that a human re-read a
file before re-stamping, or who authored a change (git carries authorship).
`architecture.md`'s body is a human-written narrative: its value is the
synthesis a newcomer builds a mental model from, so keep it prose-first and let
the ADRs carry the durable detail -- never generate the narrative from the
structured data.

## Downstream

`/make-issues` reads the features + the ADR frontmatter records and stamps each
issue with `trace_adr` (its governing decision); `/do-work` builds from those
issues. Change flows forward: add/supersede an ADR here -> re-run `/make-issues`
to reconcile.

Optionally, once the architecture is settled, `/make-data-flows` embeds per-feature
data-flow and user-flow diagrams (Mermaid) into the feature specs, and
`/make-api-contracts` derives a mock-ready OpenAPI contract from them (referencing this
layer's integrations/ADRs by id via `x-integration` / `x-trace-adr`, never redefining an
external provider). Both are **advisory** -- they never gate the build.

## Writing rules

Plain words, short sentences, no marketing language. One decision per ADR. Never use
an em dash; use a spaced double hyphen ` -- ` for asides. Be honest about trade-offs
and about which choices are still assumptions.
