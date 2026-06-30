---
# Minimal make-spec feature data file -- make-arch only reads requirements[].governed_by
# from here (the no-orphan cross-check, A-004).
meta:
  doc_type: spec-feature
  slug: checkout
  prefix: CHK
  status: active
requirements:
  - id: "FR-CHK-001"
    governed_by:
      - "ADR-0001"
    status: active
  - id: "FR-CHK-002"
    governed_by:
      - "ADR-0003"
    status: active
---

# checkout

Human narrative; the frontmatter above is the signed contract.
