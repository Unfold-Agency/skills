---
meta:
  doc_type: spec-feature
  schema_version: '1.0'
  slug: checkout
  prefix: CHK
  title: Checkout and payment
  status: active
  fingerprint: fixture
supports: [G-001, G-002]
requirements:
- id: FR-CHK-001
  name: Place order
  kind: functional
  description: The system turns a cart into a paid order.
  governed_by: [ADR-0001]
  depends_on: [FR-CART-001]
  status: active
- id: IR-CHK-001
  name: Fulfillment sync
  kind: integration
  description: Paid orders reach the fulfillment system.
  governed_by: []
  depends_on: []
  status: active
- id: NFR-CHK-001
  name: Cardholder data at rest
  kind: nonfunctional
  description: Sensitive payment data is protected.
  governed_by: []
  depends_on: []
  status: superseded
---

# Checkout and payment

Human narrative. NFR-CHK-001 is superseded (it should render dimmed).
