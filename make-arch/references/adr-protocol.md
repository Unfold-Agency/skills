# ADR Protocol (append-only decisions)

The architecture layer stays in sync with reality because its decisions are
**immutable, append-only records** -- not prose someone edits. This is the core
move that makes ADRs better than a Technical Design Document for the "which payment
processor are we using?" question: each decision is a frozen, dated, citable record,
and the answer is always findable in ≤ 2 hops (feature requirement -> `governed_by`
ADR).

## The rules

1. **One decision per file.** `decisions/ADR-NNNN-<slug>.md`, Nygard format: Status,
   Context, Decision, Consequences, Rejected alternatives (see
   `assets/adr-template.md`).
2. **Number in order, never reuse.** `ADR-0001`, `ADR-0002`, ... The validator pins
   the format (`^ADR-\d{4}$`), requires the frontmatter `id` to match the filename
   (A-002), and -- via the append-only baseline (A-008) -- refuses to let an ADR
   that existed at `origin/main` vanish. Each file's **frontmatter is its machine
   record** (id, title, status, date, scope, confidence, supersedes,
   superseded_by, governs); there is no separate index to keep in sync.
3. **Never edit an accepted decision.** Once accepted, the file is frozen -- and
   the validator enforces it mechanically: A-009 diffs every baseline-accepted ADR
   against `origin/main` and fails on ANY change except the one allowed edit, the
   **supersede transition**. To change course you write a **new** ADR that
   **supersedes** it:
   - The new ADR's frontmatter sets `supersedes: ADR-MMMM`; its Context explains why.
   - The old ADR's frontmatter gets exactly two field changes -- `status:
     superseded` and `superseded_by: ADR-NNNN`. Its prose is never touched. The
     validator (A-003) checks that a superseded ADR points at a real, different,
     non-proposed ADR.
   - The old file **stays** -- the supersession chain is the history.
4. **Status lifecycle:** `proposed` -> `accepted` -> (`superseded` | `deprecated`).
   `proposed` ADRs are exempt from the no-orphan check; an `accepted` feature-scoped
   ADR must be referenced by ≥ 1 feature requirement's `governed_by` (A-004), or it
   is an orphan -- a decision governing nothing.
5. **Scope.** `feature` ADRs decide how a feature is built and must be referenced by
   a feature. `project` ADRs are cross-cutting (repo layout, CI, auth strategy) and
   are exempt from the reference requirement (the validator only warns if one is
   unreferenced).

## How a decision is made, changed, reversed

- **New decision** (choose Stripe): add `ADR-NNNN` (Accepted, with rejected
  alternatives), add/adjust the affected components in `architecture.md`, and link
  it from the governing feature requirement's `governed_by`. Record it in the spec
  CHANGELOG.
- **Refine a decision while still Proposed:** editing is fine -- it is not yet
  frozen. Once Accepted, it is.
- **Reverse a decision:** write the superseding ADR (rule 3). Downstream,
  `make-issues` opens refactor issues for merged work that the reversed decision
  invalidated.

## Confidence and ADRs

An ADR carries `confidence: known | assumption` like every other choice (see
`recommend-then-refine.md`). An `assumption` ADR is a deliberate, reversible
placeholder -- the cheapest way to keep moving while flagging that a human should
confirm the call. Promote it with a tiny **superseding** ADR once confirmed (an
accepted ADR's confidence field is frozen like the rest of it, A-009) rather than
silently treating the guess as settled.
