---
doc_type: spec-arch
project_name: Fixture Storefront
status: draft
data_file: arch-data.yaml
---

# Architecture -- Fixture Storefront

A storefront where shoppers build a cart and pay; orders sync to fulfillment.

## System context

```mermaid
C4Context
  title System context
  Person(shopper, "Shopper")
  System(store, "Storefront", "Cart + checkout")
  System_Ext(stripe, "Stripe", "Payments")
  Rel(shopper, store, "Browses and buys")
  Rel(store, stripe, "Creates payment intents")
```

## Components

- **Storefront web app** (Next.js) -- catalog, cart, checkout. _Confidence: known._
- **Orders service** (Node + Postgres) -- orders + fulfillment sync. _Confidence: **assumption** (pending confirmation)._

## Decisions

See `decisions/` for the full ADR log. Accepted: ADR-0001 (Stripe), ADR-0003
(hosted checkout). ADR-0002 was superseded by ADR-0003.
