---
meta:
  doc_type: spec-feature
  schema_version: '1.0'
  slug: cart
  prefix: CART
  title: Cart management
  status: active
  appetite: 1 week
  feature_version: 14e31bef10f8
  generated_at: '2026-06-29T00:00:00Z'
  fingerprint: 14e31bef10f8da0a586590759f82fe73a3712d3067fa9b9cdf2a86b56d9167d6
user_stories:
- As a shopper, I want to add and remove items, so that I can assemble an order.
no_gos:
- No saved carts across devices in this phase.
supports:
- G-001
requirements:
- id: FR-CART-001
  name: Add to cart
  kind: functional
  description: The system maintains a running cart for the session.
  acceptance_criteria:
  - WHEN a user adds an item, the system shall update the cart total.
  - IF the item is out of stock, THEN the system shall prevent the add and show availability.
  governed_by: []
  depends_on: []
  interface: 'cart: { items: [{sku, qty}], total }'
  priority: must
  architecture_hints: ''
  related_files: []
  notes: ''
  status: active
- id: CR-CART-001
  name: Empty cart message
  kind: content
  description: The empty cart shows a localized helper message.
  acceptance_criteria:
  - The system shall present a localized empty-cart message.
  governed_by: []
  depends_on: []
  interface: ''
  priority: should
  architecture_hints: ''
  related_files: []
  notes: ''
  status: active
---

# Cart management

<!-- Frontmatter is the signed contract; this body is human narrative. -->

**Story.** As a shopper, I want to add and remove items, so that I can assemble an order.

**No-gos.** No saved carts across devices in this phase.

The cart maintains a running session total (`FR-CART-001`) and shows a localized
helper message when empty (`CR-CART-001`).
