# Diagram kinds -- data flows vs user flows

Two kinds of flow, each with a default Mermaid diagram type. Keep every diagram
legible: one concern per flow, and split a sprawling feature into several named
flows rather than one wall of nodes. All diagrams are ` ```mermaid ` fenced blocks
so they render in GitHub and the Claude apps.

## DATA flows (`kind=data`, id `DF-<PREFIX>-NN`)

How data moves through the feature -- the calls made, the systems touched, the
payloads that cross each edge. This is the primary aid for a backend engineer.

- **`sequenceDiagram` (default)** -- the call/response order across participants
  (user, our components, external systems). Best when timing/ordering matters.

  ```mermaid
  sequenceDiagram
    participant U as Shopper
    participant S as Storefront
    participant P as Payments
    U->>S: Submit order
    S->>P: Create charge
    P-->>S: Charge succeeded
    S-->>U: 201 Order created
  ```

- **`flowchart` / `graph`** -- when the shape is branching data movement rather than
  a strict call sequence (validation gates, fan-out to queues).

- **`erDiagram`** -- rare at feature altitude; only when the feature introduces a
  data shape that is genuinely non-obvious and local to it. The **system** data
  model belongs to make-arch, not here.

Label each edge with the payload or call (`POST /orders { items, total }`) so the
data-flow doubles as the seam make-api-contracts reads.

## USER flows (`kind=user`, id `UF-<PREFIX>-NN`)

The path a person walks through the feature -- screens, decisions, dead ends. This
is the primary aid for a frontend/product engineer.

- **`flowchart TD` (default)** -- steps and branches, including the failure path
  (every FR has an unwanted-behavior criterion; show where it lands).

  ```mermaid
  flowchart TD
    A[View cart] --> B{Signed in?}
    B -- yes --> C[Checkout]
    B -- no --> D[Sign in] --> C
    C --> E{Payment ok?}
    E -- yes --> F[Confirmation]
    E -- no --> G[Show error] --> C
  ```

- **`journey`** -- when the point is the emotional/step arc of a longer flow rather
  than branching logic.

## Coverage

Aim to cover every active functional requirement (`FR-`) with at least one flow
(data or user). `validate_flows.py` DF-004 warns about an uncovered active FR -- a
warning, not a failure, because flows are advisory. Reference the requirement id(s)
each flow covers in its `covers=` attribute.
