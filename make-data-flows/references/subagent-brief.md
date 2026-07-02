# The per-feature worker brief

For a run covering N features, spawn one worker sub-agent per **actionable** feature
(CREATE or REGENERATE, in scope). Each worker models one feature in a focused context
and returns Mermaid text; the orchestrator assembles the payload and runs the single
deterministic `embed_flows.py`. Workers write no files and never touch the specs.

## What the orchestrator gives each worker

- The feature slug and requirement prefix.
- The feature's full `requirements` list (id, kind, description, EARS acceptance
  criteria, `interface`, `depends_on`, `governed_by`) and `user_stories`.
- If make-arch exists: the names of the components/integrations this feature touches
  (so flows reference real system labels, not invented ones).
- For a REGENERATE, the feature's existing flows (so the worker reuses what still holds
  and changes only what the requirement change affected, keeping ids stable).

## The brief

> **Model the data flows and user flows for feature `<slug>` (`<PREFIX>`). Return
> Mermaid only.**
>
> 1. Read the requirements below. Decide the smallest set of legible flows that covers
>    every active functional requirement (`FR-`): usually one DATA flow and one USER
>    flow, more only when the feature has genuinely distinct concerns.
> 2. DATA flows: `sequenceDiagram` (default), each edge labelled with the call/payload
>    (e.g. `POST /orders { items, total }`). USER flows: `flowchart TD` (default),
>    including the failure branch drawn from each `IF ... THEN` criterion.
> 3. Reference make-arch component names where given; do not redraw the system context
>    or restate an ADR (that is make-arch's altitude).
> 4. Do not invent behavior the requirements do not state -- draw what the spec says and
>    flag any gap.
> 5. Return a JSON array of flows, each: `{ "id": "DF-<PREFIX>-NN" | "UF-<PREFIX>-NN",
>    "kind": "data" | "user", "covers": [requirement ids], "title": "<short>",
>    "mermaid": "<the fenced block's inner source, no ``` fences>" }`.
>
> Requirements: `<the feature's requirements>`
> Components (if any): `<names from make-arch>`
> Existing flows (REGENERATE only): `<current flows>`

## Assembling the payload

Collect each worker's JSON array under its slug into the embed payload:

```json
{"features": {"<slug>": {"flows": [ ...the worker's array... ]}}}
```

Then run `python scripts/embed_flows.py docs/product payload.json` once for the whole
run. Validate, then report. Consolidation and the write stay central and deterministic;
only the modelling fans out.
