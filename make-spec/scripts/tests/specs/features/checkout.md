---
meta:
  doc_type: spec-feature
  schema_version: '1.0'
  slug: checkout
  prefix: CHK
  title: Checkout and payment
  status: active
  appetite: 2 weeks
  feature_version: ab13cf7fc0d4
  generated_at: '2026-06-29T00:00:00Z'
  fingerprint: ab13cf7fc0d45e1e0fdd31efd49e250ef1e8229186ee3cbf329ac5aaa8c9a7f1
user_stories:
- As a shopper, I want to pay quickly, so that I can complete my order.
no_gos:
- No stored payment methods in this phase.
supports:
- G-001
- G-002
requirements:
- id: FR-CHK-001
  name: Place order
  kind: functional
  description: The system turns a cart into a paid order.
  acceptance_criteria:
  - WHEN the user confirms the order, the system shall create a payment intent.
  - IF the payment is declined, THEN the system shall display a recoverable error
    and retain the cart.
  governed_by: []
  depends_on:
  - FR-CART-001
  interface: 'order: { id, items, amount, status }'
  priority: must
  architecture_hints: ''
  related_files: []
  notes: ''
  status: active
- id: IR-CHK-001
  name: Fulfillment sync
  kind: integration
  description: Paid orders reach the fulfillment system.
  acceptance_criteria:
  - The system shall record each paid order in the fulfillment system within 5 minutes.
  governed_by: []
  depends_on: []
  interface: POST /orders { id, items, amount }
  priority: must
  architecture_hints: ''
  related_files: []
  notes: ''
  status: active
- id: NFR-CHK-001
  name: Cardholder data at rest
  kind: nonfunctional
  description: Sensitive payment data is protected.
  acceptance_criteria:
  - The system shall encrypt cardholder data at rest.
  governed_by: []
  depends_on: []
  interface: ''
  priority: must
  architecture_hints: ''
  related_files: []
  notes: ''
  status: active
---

# Checkout and payment

<!-- The frontmatter above is the signed source of truth: the machine-readable
contract (requirements, EARS acceptance criteria, dependencies, the stamped
fingerprint). This body is human narrative for reviewers; it must not introduce
contract claims that are not in the frontmatter. -->

**Story.** As a shopper, I want to pay quickly, so that I can complete my order.

**No-gos.** No stored payment methods in this phase.

This feature turns a confirmed cart into a paid order (`FR-CHK-001`, depends on
the cart's `FR-CART-001`), records each paid order in fulfillment within five
minutes (`IR-CHK-001`), and keeps cardholder data encrypted at rest
(`NFR-CHK-001`).
