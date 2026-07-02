<!--
═══════════════════════════════════════════════════════════════════
ADR TEMPLATE -- docs/product/decisions/ADR-NNNN-<slug>.md   (make-arch)

One file per decision (Michael Nygard's ADR format). The YAML
FRONTMATTER is the machine record -- the index entry downstream tools
read (make-issues snippets, make-trace, make-api-contracts); there is
no separate index file. The body is the human prose.

The ADR log is APPEND-ONLY and immutable: once a decision is accepted
you NEVER edit it. To change a decision, write a NEW ADR that
supersedes it. The ONE allowed edit to an accepted ADR is the
supersede transition itself -- set `status: superseded` (or
`deprecated`) and `superseded_by: ADR-MMMM`; anything else fails the
validator (A-009). The chain of supersessions is the history.

Numbering: four digits, assigned in order (ADR-0001, ADR-0002, ...).
Never reused or deleted (A-002/A-008). The frontmatter `id` must match
the filename.

Confidence: `known` (backed by a requirement, constraint, or client
fact -- cite it in Context) or `assumption` (a default pending
confirmation). Assumption-backed ADRs are where a human looks first.

Strip these authoring comments before publishing. Never an em dash;
use ` -- `.
═══════════════════════════════════════════════════════════════════
-->

---
id: ADR-NNNN
title: "[Decision title, imperative: Use X for Y]"
status: proposed            # proposed | accepted | superseded | deprecated
date: "YYYY-MM-DD"
scope: feature              # feature | project
confidence: known           # known | assumption
supersedes: ""              # ADR-MMMM, only if this one replaces another
superseded_by: ""           # set ONLY by the supersede transition (A-009)
governs: []                 # informational: requirement ids / feature slugs
---

# ADR-NNNN -- [Decision title]

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
