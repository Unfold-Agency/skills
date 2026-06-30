<!--
═══════════════════════════════════════════════════════════════════
ADR TEMPLATE — docs/specs/decisions/ADR-NNNN-<slug>.md   (make-arch)

One file per decision (Michael Nygard's ADR format). The ADR log is
APPEND-ONLY and immutable: once a decision is Accepted you NEVER edit it.
To change a decision, write a NEW ADR that supersedes it -- the old one
stays, with its Status updated to "Superseded by ADR-MMMM". This is why
the architecture layer stays in sync: every decision is a frozen record,
and the chain of supersessions is the history.

Numbering: four digits, assigned in order (ADR-0001, ADR-0002, ...).
Never reused or deleted (validator A-002/A-008).

Confidence: state whether the decision is `known` (backed by a
requirement, constraint, or client fact -- cite it) or an `assumption`
(a default pending confirmation). Assumption-backed ADRs are where a
human should look first.
═══════════════════════════════════════════════════════════════════
-->

# ADR-NNNN — [Decision title, imperative: "Use X for Y"]

- **Status:** Proposed | Accepted | Superseded by ADR-MMMM | Deprecated
- **Date:** YYYY-MM-DD
- **Confidence:** known (cite the source) | assumption (state what would confirm it)
- **Scope:** feature | project
- **Supersedes:** ADR-MMMM   <!-- only if this one replaces another -->

## Context

<!-- The forces at play: the requirements, constraints, and facts that
make this a real decision. What problem are we deciding, and why now?
Cite feature requirement IDs / constraints where they drive the choice. -->

## Decision

<!-- The choice, stated plainly. "We will use ___." One decision per ADR. -->

## Consequences

<!-- What becomes easier and what becomes harder. The trade-off we are
accepting, the new dependencies, the things we now have to live with.
Honest about the downsides -- that is the whole point of recording it. -->

## Rejected alternatives

<!-- The options considered and why each lost. This is what makes the ADR
worth reading later: it shows the decision was real, not a default. -->

- **[Alternative]** -- rejected because [reason].
