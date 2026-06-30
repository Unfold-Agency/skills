# ADR-0001 — Use Stripe for payments

- **Status:** Accepted
- **Date:** 2026-06-29
- **Confidence:** known (the client already runs Stripe)

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
