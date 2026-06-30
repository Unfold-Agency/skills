---
doc_type: spec-feature
slug: checkout
prefix: CHK
title: Checkout and payment
status: active
appetite: 2 weeks
data_file: features/checkout-data.yaml
---

# Checkout and payment

**Story.** As a shopper, I want to pay quickly, so that I can complete my order.

**No-gos.** No stored payment methods in this phase.

## FR-CHK-001 — Place order
The system turns a cart into a paid order. Depends on FR-CART-001.

- WHEN the user confirms the order, the system shall create a payment intent.
- IF the payment is declined, THEN the system shall display a recoverable error and retain the cart.

## IR-CHK-001 — Fulfillment sync
Paid orders reach the fulfillment system.

- The system shall record each paid order in the fulfillment system within 5 minutes.

## NFR-CHK-001 — Cardholder data at rest
Sensitive payment data is protected.

- The system shall encrypt cardholder data at rest.
