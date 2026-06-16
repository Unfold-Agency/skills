# Intake & Questioning (Generate Mode)

How to turn an approved PRD plus system context into a sourced, traceable TDD draft. The prime directive: **recommend, then refine -- take a position from what is known, never interrogate the engineer from a blank page.** The engineer reacts to a recommendation faster and better than they answer a cold question.

## 1. PRD and corpus intake

Read the PRD first -- both files: `PRD.md` (the prose people signed) and `prd-data.yaml` (the IDs you will trace to). The PRD is the source of truth for WHAT; this document only decides HOW.

- **Confirm the PRD is `approved`.** If its status is still `draft` or `in-review`, say so and warn: designing against an unapproved PRD risks rework when the WHAT moves under you. Proceed only if the user accepts that risk, and note it as a risk (`RISK-`).
- **Lock to the PRD version.** Record the PRD's version in `meta.prd_version`. The PRD may have jumped several versions before the TDD existed -- lock to whatever the latest is. This lock is what lets the downstream `make-issues` trust the TDD: it refuses to run when the TDD's `prd_version` no longer matches the live PRD. If you re-open this TDD later and the PRD has moved on, the TDD is stale (V-017) and must be amended and re-locked.
- **Resolve every item the PRD flagged "for the TDD."** Those are the open HOW questions this document exists to answer. Pull them from the PRD's conflicts/decisions log and constraints.
- **Inventory the system context** into Appendix A (Source Index) with stable handles -- the existing architecture you must fit into, not the discovery corpus.

| Source type | Handle | Locator to capture |
|---|---|---|
| Existing ERD / schema | `ERD-n` | table or entity name |
| Existing ADR / design doc | `ADR-doc-n` | decision title or section |
| Third-party API docs | `API-name` | endpoint or section |
| Tech / brand / platform standards | `STD-n` | section or rule |
| Architecture notes / diagrams | `DOC-n` | figure or heading |

Assess each source's citation strength and work with what it has. **Never invent a locator;** a vague-but-true locator beats a precise-but-fabricated one. A claim that rests only on an uncitable source is an assumption (`ASM-`), not a fact.

Establish the system of record on this run (a freshly generated TDD is born `system_of_record: claude-project`). See SKILL.md, *Location & system of record*, for the full reconciliation -- it runs on every invocation, generate included.

## 2. Form the position

From the PRD requirements plus clearly stated assumptions, draft a recommended architecture across **all** TDD sections -- data models, behavioral and process models, integrations, decisions, NFRs. Do not wait for the engineer to ask.

- **Tag every recommendation `known-backed` or `assumption-backed`** so the engineer can see what is load-bearing. A choice the PRD's facts settle is known-backed; a choice resting on something unconfirmed is assumption-backed, and its assumption gets an `ASM-` id with an owner.
- A recommendation with no backing at all is not a recommendation -- it is an open question (`OQ-`).
- **Extract the binding constraints** you can infer from the PRD constraints (`CON-`) and the stated stack. "Client runs Shopify Plus" is a binding constraint (`BC-`), not a decision. Each `BC-` needs a source.

## 3. The refine loop

Present the position and invite changes. Three behaviors are required on **every** pass -- skipping any one is how a TDD ends up confident and wrong:

1. **State the gaps.** Always name what is missing or unclear -- an objective with no design answer, a flow with an undefined failure path, an integration with an unknown rate limit. The engineer needs to see the holes, not discover them at build time.
2. **Surface what must be true.** Identify the binding constraints the design is bound by -- version requirements, licensing restrictions, platform and runtime mandates, compliance-driven technical requirements. These are not up for debate; the engineer confirms them and the design respects them. An unconfirmed must-be-true is an assumption until confirmed.
3. **Pose decisions as recommendation + rationale + tradeoff + question.** So the engineer overrides rather than originates:
   > *Recommend Remix for the storefront (SSR serves the SEO requirement, the team knows it). Tradeoff: heavier than a static build, and it adds a server to operate. Use it, or do you want a static-first approach?*
   Capture every override as a decision record (`ADR-`): decision, rationale, alternatives considered, what it serves (`derived_from`), and any `BC-` it is bound by.

## 4. Question discipline

Batch the highest-value open decisions into one pass, **capped at ~7**, highest leverage first -- matching the PRD question pass. Run a second round only when an answer opens a genuinely new fork.

- Everything not asked becomes a recorded **assumption** (`ASM-`, owner `TBD`) the design proceeds on, or an **open question** (`OQ-`) if it blocks a design element. The difference: you can build on an assumption; an open question must be answered first.
- **Do not block generation waiting for answers.** Ship v0.1 with honest assumptions and a populated Open Questions section. A long Section 13 in v0.1 is healthy; a long one at approval is not.

## 5. Diagrams

Model visually, in Mermaid (the Lane 3 convention):

- One ERD for the data model (Section 4); a `stateDiagram` per stateful object (Section 5); a `sequenceDiagram` per key workflow (Section 6).
- **Show failure branches, not just happy paths** -- a flow that only diagrams success is not done. Inferring a failure branch from stated behavior is allowed; inventing new behavior is not.
- Each diagrammed record sets `needs_diagram: true` in the data file; validator rule V-008 confirms a matching Mermaid block exists in the Markdown.

## 6. Output hygiene

- Strip every HTML guidance comment from the final Markdown. Write Section 2 (Summary) last, plain words.
- Default NFRs (accessibility, security, observability) stay unless the user explicitly waives them; record any waiver in the changelog.
- Derive `tdd-data.yaml` **in chunks** -- write `meta` first, then one record collection at a time (entities, then state machines, then workflows, ...), appending each. Emitting the whole file in one step times out and blows the context window on a real design. Then run:
  ```
  python scripts/validate_tdd.py tdd-data.yaml --prd prd-data.yaml --tdd-md TDD.md
  ```
  `--prd` enforces both coverage and the PRD version lock (V-017). Fix every failure before presenting. Stamp `meta.fingerprint` and set `system_of_record`. Never present a TDD whose data file fails validation, and **never write `status: approved`** -- that is the human review gate.
- Report to the user: capability count; **requirement coverage** (PRD `must`/`should` mapped vs. unmapped); binding-constraint count; open assumption count; open risk count; and anything you routed somewhere they might not expect (a "requirement" demoted to an assumption, a decision left as an open question).
