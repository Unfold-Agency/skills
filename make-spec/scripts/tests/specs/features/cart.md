---
doc_type: spec-feature
slug: cart
prefix: CART
title: Cart management
status: active
appetite: 1 week
data_file: features/cart-data.yaml
---

# Cart management

**Story.** As a shopper, I want to add and remove items, so that I can assemble an order.

**No-gos.** No saved carts across devices in this phase.

## FR-CART-001 -- Add to cart
The system maintains a running cart for the session.

- WHEN a user adds an item, the system shall update the cart total.
- IF the item is out of stock, THEN the system shall prevent the add and show availability.

## CR-CART-001 -- Empty cart message
The empty cart shows a localized helper message.

- The system shall present a localized empty-cart message.
