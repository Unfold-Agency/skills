# Kickoff -- generating flows for a feature that has none

A feature with no `make-data-flows:flows` region yet. `flow_status.py` reports it as
**CREATE**. The goal: one or more legible data flows and user flows that cover the
feature's active requirements, each traced to the requirement id(s) it visualizes.

## Steps

1. **Read the feature.** Its `requirements` (id, description, EARS acceptance criteria,
   `interface`, `depends_on`, `governed_by`), its `user_stories`, and -- if `make-arch`
   exists -- the component/integration names the feature touches (so flows reference
   real system labels, per `boundary-with-arch.md`).
2. **Decide the flows.** Usually one DATA flow and one USER flow per feature; add more
   when the feature has distinct concerns (e.g. a happy path and a refund path). Do not
   force multiples where one clear diagram suffices. Every active `FR-` should be
   covered by at least one flow (DF-004).
3. **Author the Mermaid** per `assets/diagram-kinds.md`:
   - DATA -> `sequenceDiagram` (default), edges labelled with the call/payload.
   - USER -> `flowchart TD` (default), including the failure branch from the
     requirement's `IF ... THEN` criterion.
4. **Assign ids.** `DF-<PREFIX>-NN` / `UF-<PREFIX>-NN`, numbered from 01, using the
   feature's requirement prefix.
5. **Emit the payload** (Mermaid text + `covers` + `kind` + optional `title`) and let
   `embed_flows.py` write the region. Do not hand-write the region.

## Fan-out

For a run covering several features, spawn **one worker sub-agent per feature** (the
brief is `references/subagent-brief.md`) so each feature is modelled by a focused
context; the orchestrator assembles the payloads and runs the single deterministic
embed. A worker returns Mermaid text only -- it never writes files.

## Keep it honest

A flow is a model's reading of the requirements. Where the requirements are silent on a
step (an error path, a retry, an external call), do not invent behavior to make the
picture tidy -- draw what the spec says and note the gap in your report, the same way
make-spec surfaces open questions. If a flow needs a decision that is not yet an ADR,
say so and point at `/make-arch`.
