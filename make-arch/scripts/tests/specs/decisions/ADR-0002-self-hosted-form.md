# ADR-0002 -- Use a self-hosted payment form

- **Status:** Superseded by ADR-0003
- **Date:** 2026-06-20
- **Confidence:** known

## Context
An early proposal to render our own card form for maximum UX control.

## Decision
Render a self-hosted card form posting to our backend.

## Consequences
- Full UX control, but the backend enters PCI-DSS scope.

## Rejected alternatives
- Hosted checkout (later adopted as ADR-0003).

> Superseded by **ADR-0003**: the PCI burden was judged not worth the control.
> This record is kept (append-only); it is never edited away.
