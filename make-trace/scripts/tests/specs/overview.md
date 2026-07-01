---
meta:
  doc_type: spec-overview
  schema_version: '1.0'
  project_id: proj-fixture
  project_name: Fixture Storefront
  project_version: '0.1'
  mode: full
  status: draft
  fingerprint: fixture
goals:
- id: G-001
  kind: business
  statement: Lift completed-checkout rate.
  metric: Checkout completion rate >= 70% at p50.
  measurement_method: Funnel analytics.
  status: active
- id: G-002
  kind: user
  statement: Shoppers trust the payment step.
  metric: Payment-step error rate < 2%.
  measurement_method: Client-side error events.
  status: active
feature_index:
- slug: cart
  prefix: CART
  title: Cart management
  status: active
- slug: checkout
  prefix: CHK
  title: Checkout and payment
  status: active
---

# Fixture Storefront -- Spec Overview

Human narrative; the frontmatter above is the signed contract.
