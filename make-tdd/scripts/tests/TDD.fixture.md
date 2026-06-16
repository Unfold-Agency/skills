---
doc_type: TDD
version: "0.1"
status: draft
---

# Test Project — Technical Design Document

## 4. Data Models

```mermaid
erDiagram
  ORDER ||--|{ LINE_ITEM : contains
```

#### ENT-001 — Order
- Purpose: a customer order.

## 5. Behavioral Models

#### STM-001 — Order lifecycle

```mermaid
stateDiagram-v2
  [*] --> draft
  draft --> submitted
```

## 6. Process Flows

#### WF-001 — Checkout

```mermaid
sequenceDiagram
  actor U as User
  participant A as App
  U->>A: checkout
  A-->>U: confirmation
```
