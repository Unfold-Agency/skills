---
name: make-tdd
description: Generate and amend Technical Design Documents (TDDs) for agency projects, translating an approved PRD into system architecture using Mondo Robot's TDD template and the RFEF Lane 3 process. Use this skill whenever the user wants to design the architecture, model the system, decide the stack, define data models / state machines / sequence diagrams / API contracts, resolve items the PRD flagged "for the TDD," or amend an existing TDD against a change. Trigger it even if the user says "technical design," "system design," "architect this," "how should we build this," or "spec out the HOW." Do NOT use for the PRD (upstream -- use make-prd) or for ticket generation (downstream -- use make-plan).
---

# Make a TDD

Build and maintain TDDs as the single source of truth for HOW an agency project is built. A TDD here is two files with one meaning: a human-authored Markdown document (the thing people read, review, and sign) and a derived `tdd-data.yaml` (the thing the ticket generator consumes). The Markdown wins every disagreement; the YAML is regenerated, never hand-edited.

This skill has two modes. Decide which one applies before doing anything else:

- **Generate mode** -- no TDD exists yet. Input is the approved PRD plus system context; output is TDD v0.1 (draft).
- **Amend mode** -- a TDD exists. Input is a change trigger (PRD amendment, build blocker, vendor change, discovery). Output is a new version with propagation guidance. Never regenerate from scratch when amending; diff, don't rewrite.

The doctrine that governs everything: the TDD states **HOW**; the PRD owns **WHAT and WHY**. Objectives, requirements, and constraints live upstream; system structure, stack and vendor choices, and the rationale behind them live here. An item the PRD flagged "for the TDD" gets resolved here. A binding fact of the client's world (a platform mandate, a license limit) is a constraint, not a decision. Three rules are absolute: every capability traces to a PRD requirement ID; every decision and NFR derives from a requirement or a recorded assumption (no orphan architecture); and you **recommend, then refine** -- take a position from the knowns, label what rests on assumptions, and never invent certainty. Version starts at 0.1, status `draft`. Only a human moves it to `approved` -- that is the architecture-review gate; the skill never self-approves.

## Files in this skill

- `assets/TDD-template.md` -- the master template. Read it in full before generating. Its HTML comments are the per-section authoring instructions; follow them, then strip them from the output.
- `assets/tdd-data-schema.yaml` -- the schema for the derived data file, including the ID prefixes, the `meta` system-of-record fields, and validator rules V-001 through V-016. Read it before deriving the YAML.
- `references/intake-and-questioning.md` -- read in Generate mode: PRD and system-context intake, the recommend-then-refine method, gap and constraint surfacing, the question cap, citation discipline, output hygiene.
- `references/amendment-protocol.md` -- read in Amend mode: the location guard, change classification, version bumping, propagation.
- `scripts/validate_tdd.py` -- run after every YAML derivation: `python scripts/validate_tdd.py <tdd-data.yaml> [--prd <prd-data.yaml>] [--tdd-md <TDD.md>] [--prev <previous-tdd-data.yaml>]`. Requires PyYAML (`pip install pyyaml --break-system-packages` if missing). Exit code 0 = pass. Never present a TDD whose data file fails validation; fix or downgrade items (an unsupported "requirement" becomes an assumption or an open question) until it passes, and tell the user about anything you downgraded.

## Mode selection (first action)

Look for an existing TDD (both files) and a change trigger. A change trigger plus an existing TDD means Amend mode; an approved PRD and no TDD means Generate mode. Then, before editing anything in either mode, run the location guard below -- it decides whether you are even allowed to write here.

## Generate mode workflow

1. **PRD and system-context intake first.** Read the PRD (`PRD.md` + `prd-data.yaml`) and confirm its status is `approved`; if it is still `draft`, warn the user that designing against an unapproved PRD risks rework, and record the risk. Inventory system context (existing ERDs, ADRs, API docs, standards) into the Source Index with stable handles. Read `references/intake-and-questioning.md` now. A newly generated TDD is born with `system_of_record: claude-project`.
2. **Form the position.** From the PRD requirements plus stated assumptions, draft the recommended architecture across all TDD sections. Tag each recommendation known-backed or assumption-backed. Extract every binding constraint you can infer from the PRD constraints and the stated stack; each gets a source.
3. **Refine pass.** Present the recommendations and invite changes. Every pass does three things: **state the gaps** (objectives with no design answer, flows with undefined failure paths, integrations with unknown limits); **surface what must be true** (the binding constraints the design is bound by -- version requirements, licensing, platform mandates, compliance); and **pose the high-leverage open decisions** (cap ~7) as recommendation + rationale + tradeoff + question. Record overrides as decision records (`ADR-`). Unanswered items become assumptions (`ASM-`, owner TBD) or open questions (`OQ-`) if they block.
4. **Write the Markdown.** Fill the template. Embed diagrams as Mermaid (ERD, state machines, sequence flows), each with a failure branch where one exists. Strip all HTML guidance comments. Default NFRs (accessibility, security, observability) stay in unless explicitly waived -- record any waiver in the changelog.
5. **Derive and validate.** Generate `tdd-data.yaml` per the schema, stamp `meta.fingerprint`, run `validate_tdd.py` with `--prd` pointed at `prd-data.yaml` and `--tdd-md` at the Markdown, fix failures, and report: capability count, requirement coverage (mapped vs. unmapped PRD IDs), binding-constraint count, open assumption count, open risk count, and anything you routed somewhere the user might not expect.

## Amend mode workflow

1. Read `references/amendment-protocol.md`, the existing TDD (both files), and the change trigger. **Run the location guard (below) before editing anything.** If the trigger references material you don't have (the PRD amendment, the failing ticket, the vendor notice), gather it first.
2. **Classify the change:** refinement (alters no ID'd item -- tell the user and stop), minor (additive/clarifying, x.Y bump), or major (changes the meaning of an existing decision, contract, model, or binding constraint -- X.0 bump, approval required).
3. **Apply the diff.** Never renumber or delete IDs -- supersede or defer them. Record the change in the changelog with class, changed IDs, and trigger reference.
4. **Re-derive and validate with `--prev`** pointed at the prior data file (this enforces the no-vanishing-IDs rule, V-009). Regenerate the fingerprint.
5. **Report propagation.** For major amendments, output the impact list: changed IDs, any newly unmapped requirements, which downstream tickets reference them (tickets are pinned to the prior TDD version), and the steps still owed. The skill prepares propagation; humans execute the approvals.

## Location & system of record

The PRD and TDD are often drafted in the Claude Desktop app and saved to a Claude Project, before a GitHub repo exists. Later the TDD is pulled into a repo for the build. The risk is two editable copies drifting apart -- a team working from Claude Chat versus a team working from Claude Code. This is the guardrail; run it on **every** invocation, in both modes, before writing.

Establish two facts: **where am I running** (in Claude Code, check `git rev-parse --is-inside-work-tree` and whether the TDD file is tracked) and **what does the document say its system of record is** (`meta.system_of_record`). Then reconcile:

| Record says | Running in | Action |
|---|---|---|
| `claude-project` | the Project | proceed normally |
| `claude-project` | inside a repo | **promotion event** -- flip `system_of_record` to `git`, set `repo` (url + path), set `promoted_at`, regenerate the fingerprint, and instruct that the Project copy be marked SUPERSEDED |
| `git` | the repo | proceed normally; regenerate the fingerprint on save |
| `git` | the Project / anywhere outside the repo | **stop.** Warn that the canonical copy lives in the repo at `meta.repo.path` and that editing here forks it. Direct the user to amend via `/make-tdd` in Claude Code. Do not silently edit. |

**Drift check.** If a `fingerprint` is recorded and the current content's recompute differs without a matching version bump, flag a possible out-of-band edit and ask the human to reconcile before proceeding.

**SUPERSEDED banner** (stamped on the stale Project copy at promotion):
```
> SUPERSEDED. The canonical TDD now lives in the repo at <path> as of <date>,
> satisfying PRD v<X>. This copy is a read-only snapshot. Do not edit --
> amend via /make-tdd in Claude Code.
```

**Honest limit.** The skill cannot lock the Project copy. It can declare, check, warn, stamp the banner, and fingerprint for drift -- the last mile is team discipline. Build the guardrail anyway; it catches the common case (someone reflexively editing the wrong copy) before it becomes a reconciliation.

## Large corpora and sub-agents

When the system context is too big to hold in one context, or to run the mechanical YAML derive/validate/fix loop inline, offload to sub-agents. The shape: one reader sub-agent per source returns a cited digest (raw API docs and ERDs stay out of the main context), then **architecture stays central** so IDs and cross-references stay consistent, and the derive+validate loop runs in its own sub-agent. Applies to both modes.

## Tone and writing rules for TDD prose

Plain words, short sentences, no marketing language. Decisions stated one at a time, each with its rationale. Never use an em dash in output; use a spaced double hyphen ` -- ` for asides. Write so the ticket generator (or an engineer outside the project) can act on each item without asking what it means.
