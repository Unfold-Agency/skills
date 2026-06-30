# ADR-0003 -- Use a hosted checkout for PCI scope reduction

- **Status:** Accepted
- **Date:** 2026-06-29
- **Confidence:** known
- **Supersedes:** ADR-0002

## Context
ADR-0002 proposed a self-hosted card form, which pulls the backend into
PCI-DSS scope. The team prefers to minimize that scope.

## Decision
Use Stripe's hosted checkout for the payment step.

## Consequences
- The backend stays out of PCI scope.
- Less control over the payment-page look and feel.

## Rejected alternatives
- The self-hosted form (ADR-0002) -- the scope cost outweighed the control.
