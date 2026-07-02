---
id: ADR-0001
title: "Use Stripe for payments"
status: accepted
date: "2026-06-29"
scope: feature
confidence: known
supersedes: ""
superseded_by: ""
governs:
  - FR-CHK-001
---

# ADR-0001 -- Use Stripe for payments

## Context
The storefront must capture card payments and reduce PCI scope. The client
already has a Stripe account and reconciles payouts there.

## Decision
Use Stripe for payment capture, via payment intents and webhooks.

## Consequences
- Card data never touches our servers (Stripe-hosted fields).
- We depend on Stripe webhook delivery for order finalization.

## Rejected alternatives
- **A self-hosted payment form** (ADR-0002) -- rejected: large PCI burden.
- **Braintree** -- no existing client relationship; no advantage here.
