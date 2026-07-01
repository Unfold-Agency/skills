# The boundary with make-arch

make-arch and make-data-flows both draw Mermaid, so the line between them must be
crisp or they overlap and contradict. The rule is **altitude**.

## make-arch draws the SYSTEM

- The C4 level-1 context and level-2 container diagrams: who/what uses the system
  and the deployable pieces.
- The **system** data model (a system-wide `erDiagram`).
- A cross-cutting sequence for a genuinely tricky system interaction.
- It names components (`C-NNN`), integrations (`INTG-`), and decisions (`ADR-`), and
  those diagrams are IN the architecture fingerprint.

## make-data-flows draws INSIDE ONE FEATURE

- How a single feature shuttles data (a `sequenceDiagram`/`flowchart` of its own
  calls) and how a user walks it (`flowchart TD`/`journey`).
- Every flow is traced to the feature's requirement id(s) via `covers=`.
- It lives in the feature body, OUT of every fingerprint.

## The one-line test

> Does it name a component, an ADR, an external system, or a system boundary?
> -> that is **make-arch**.
> Does it explain how one feature moves data or walks a user, step by step?
> -> that is **make-data-flows**.

## Don't redraw the system here

Reference make-arch's components by their label (e.g. "Payments", "Storefront") so a
reader can connect a feature flow to the system picture, but never redraw the system
context or restate an ADR inside a feature. If a flow keeps pulling in system-wide
structure, the decision it depends on belongs in an ADR (run `/make-arch`), and the
flow should reference it, not embed it.
