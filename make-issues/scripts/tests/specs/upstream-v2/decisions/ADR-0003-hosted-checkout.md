---
id: ADR-0003
title: "Use a hosted checkout for PCI scope reduction"
status: accepted
date: "2026-06-29"
scope: feature
confidence: known
supersedes: ADR-0002
superseded_by: ""
governs:
  - FR-CHK-002
---

# ADR-0003 -- Use a hosted checkout for PCI scope reduction

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
