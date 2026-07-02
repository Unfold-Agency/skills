---
meta:
  doc_type: spec-arch
  schema_version: '2.0'
  project_id: proj-fixture
  project_name: Fixture Storefront
  status: draft
  arch_version: abc123def456
  fingerprint: fixture
context: A storefront where shoppers build a cart and pay.
components:
- id: C-001
  name: Storefront web app
  responsibility: Render the catalog, cart, and checkout.
  tech: Next.js
  confidence: known
  governed_by:
  - ADR-0001
integrations:
- name: Payment gateway
  external_system: Stripe
  direction: outbound
  data: payment intents, webhooks
  confidence: known
  governed_by:
  - ADR-0001
diagrams:
- context
---

# Architecture -- Fixture Storefront

Human narrative; the frontmatter above is the signed contract.
