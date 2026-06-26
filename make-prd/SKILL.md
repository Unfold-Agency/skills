---
name: make-prd
description: Generate and amend Product Requirements Documents (PRDs) for agency projects using Mondo Robot's master PRD template and the RFEF Lane 2 process. Use this skill whenever the user wants to create a PRD, formalize requirements, turn discovery materials (RFPs, briefs, meeting notes, workshop transcripts, FigJam exports, stakeholder interviews) into a requirements document, update or amend an existing PRD, process an escalation or change request against a PRD, or validate a PRD's data file. Trigger it even if the user says "requirements doc," "FRD," "spec out the project," or "what are we building" — if the deliverable is a requirements document or a change to one, this skill applies. Do NOT use for the Brief (upstream) or the TDD (downstream).
---
 
# Make a PRD
 
Build and maintain PRDs as the single source of truth for what an agency project delivers. A PRD here is two files with one meaning: a human-authored Markdown document (the thing people read, redline, and sign) and a derived `prd-data.yaml` (the thing downstream tools consume). The Markdown wins every disagreement; the YAML is regenerated, never hand-edited.
 
This skill has two modes. Decide which one applies before doing anything else:
 
- **Generate mode** — no PRD exists yet. Input is a corpus of discovery material; output is PRD v0.1 (draft).
- **Amend mode** — a PRD exists. Input is a change trigger (escalation, UAT issue, client request, discovery). Output is a new PRD version with propagation guidance. Never regenerate from scratch when amending; diff, don't rewrite.
The doctrine that governs everything: the PRD states **WHAT and WHY, never HOW**. Architecture, vendor choices, and staffing belong in the TDD. "Client runs Shopify Plus" is a constraint and stays; "use the Shopify REST API" gets cut or demoted. When in doubt, reframe as a constraint or flag it for the TDD.
 
## Files in this skill
 
- `assets/PRD-template.md` — the master template. Read it in full before generating. Its HTML comments are the per-section authoring instructions; follow them, then strip them from the output.
- `assets/prd-data-schema.yaml` — the schema for the derived data file, including the escalation record format and validator rules V-001 through V-016. Read it before deriving the YAML or processing an escalation.
- `references/corpus-intake.md` — read first in Generate mode, and in Amend/escalation intake when the trigger material isn't supplied: scope the gather, pull from connected sources, confirm the Source Index before extracting.
- `references/extraction-guide.md` — read in Generate mode: corpus intake, citation discipline, conflict handling, the question pass.
- `references/amendment-protocol.md` — read in Amend mode: change classification, version bumping, propagation, escalation handling.
- `references/orchestration.md` — read for large corpora and before YAML derivation: read sources in parallel with sub-agents, keep extraction central, offload the derive+validate loop.
- `scripts/validate_prd.py` — run after every YAML derivation: `python scripts/validate_prd.py docs/prd-data.yaml [--prd-md docs/PRD-<project>.md] [--prev docs/archive/prd-data-v<old>.yaml]`. Requires PyYAML (`pip install pyyaml --break-system-packages` if missing). Exit code 0 = pass. Never present a PRD whose data file fails validation; fix or downgrade items (e.g., unsourced requirement → known unknown) until it passes, and tell the user about anything you downgraded.

## Location, filing & archiving

The PRD pair has one canonical home in a repo: **`docs/`**. The master Markdown is `docs/PRD-<project>.md` and the derived data file is `docs/prd-data.yaml` (shards, for large engagements, under `docs/07-requirements/`). The live files always keep these names -- the version lives in the frontmatter, never the filename; record the live path in frontmatter `data_file`. Before a repo exists the pair may live in a Claude Project; `docs/` is the repo layout.

**Archive on every bump.** In amend mode, *before* applying the diff, snapshot the outgoing version into `docs/archive/` with its version in the name -- `docs/archive/PRD-<project>-v<old>.md` and `docs/archive/prd-data-v<old>.yaml` -- then amend the live files in place and bump. The archived prior `prd-data.yaml` is exactly what the validator's `--prev` reads, so the archive is functional, not just history. Generate mode (v0.1) archives nothing.

## Generate mode workflow
 
1. **Assemble the corpus, then inventory, then extract.** If the user hasn't supplied the full corpus, read `references/corpus-intake.md` and gather within a named scope — never search the whole account. Inventory every input (gathered or supplied) into the Source Index (Appendix A) with a stable handle, and confirm that index with the user before extracting anything. If an input lacks what citations need (a transcript with no timestamps, an unnamed notes file), note it — items from weak sources get weaker locators, not invented ones. Then read `references/extraction-guide.md`; for a large corpus, read `references/orchestration.md` first.
2. **Extraction pass.** Work section by section through the template. Every extracted item gets an ID and at least one source citation (handle + locator). Three routing rules are absolute:
   - No source → the item goes to Known Unknowns (Section 11), not into Requirements.
   - Sources disagree → log the conflict in Section 13 with both sources; do not pick a winner.
   - Implementation detail ("how") → constraint if it's a fact of the client's world, otherwise flag for TDD and leave it out.
3. **Question pass.** Before writing the final draft, surface what's missing: objectives without measurable criteria, FRs without failure paths, baselines nobody stated, decision authority nobody named. Ask the user the highest-value questions (cap around 7); everything else becomes a KU- entry with an owner of "TBD". A long Section 11 in v0.1 is healthy — silence about gaps is not.
4. **Write the Markdown.** Fill the template. Write the Summary (Section 2) last. Apply Given/When/Then to every FR including at least one failure or edge path. Strip all HTML guidance comments. Default NFRs (accessibility, analytics) stay in unless the user explicitly waives them — record any waiver in Section 13.
5. **Derive and validate.** Generate `prd-data.yaml` per the schema, run the validator, fix failures, and report: item counts per section, open KU count, open conflict count, and anything you routed away from where the user might expect it.
Version starts at 0.1, status `draft`. Only a human moves it to `approved`. Once it is approved, the next lane is the design: `/make-tdd` derives the TDD and locks to this PRD version.
 
## Amend mode workflow
 
1. Read `references/amendment-protocol.md`, the existing PRD (both files), and the change trigger. If the trigger references material you don't have (the meeting where a change was decided, an email thread, a UAT report), gather it within a named scope first — `references/corpus-intake.md` applies here too.
2. **Classify the change** (this is the heart of amend mode): ticket refinement (alters no ID'd item — tell the user it doesn't touch the PRD and stop), minor (additive/clarifying, x.Y bump), or major (changes meaning of an existing item, X.0 bump, approval required).
3. **Apply the diff.** Never renumber or delete IDs — supersede or defer them. Record the change in Section 1.1 with class, changed IDs, and trigger reference. Log the decision in Section 13 if a judgment call was made.
4. **Snapshot, then re-derive.** First copy the outgoing live files into `docs/archive/` (`docs/archive/PRD-<project>-v<old>.md` and `docs/archive/prd-data-v<old>.yaml`). Then regenerate `docs/prd-data.yaml` and run the validator with `--prev docs/archive/prd-data-v<old>.yaml` (this enforces the no-vanishing-IDs rule, V-005).
5. **Report propagation.** For major amendments, output the impact list: changed IDs, which downstream artifacts reference them, and the Section 1.3 steps still owed. A PRD change reaches GitHub issues only through the TDD: re-run `/make-tdd` to re-derive and re-lock to this PRD version, then `/make-issues` to sync -- issues are pinned to a TDD version and never reconciled against the PRD directly. The skill prepares the propagation; humans execute the approvals.
## Escalations
 
When the input is an escalation (an agent or person who can't satisfy an acceptance criterion as written), create or ingest an ESC- record per the schema, then run Amend mode steps 2–5 once a human validator has decided. If validating the escalation needs material you don't have (the failing ticket's context, the relevant transcript), gather it within scope first per `references/corpus-intake.md`. The skill may propose a change class; it must never decide one. Open escalations and open conflicts both block `approved` status — the validator enforces this.
 
## Large corpora and sub-agents

When the corpus is too big to hold in one context, or to run the mechanical YAML derive/validate/fix loop inline, offload to sub-agents — read `references/orchestration.md`. The shape: one reader sub-agent per source returns a cited digest (raw transcripts stay out of the main context), then **extraction stays central** so IDs and cross-references stay consistent, and the derive+validate loop runs in its own sub-agent. Applies to both modes.

## Tone and writing rules for PRD prose
 
Plain words, short sentences, no marketing language. Requirements use "must" statements one behavior at a time. Never use an em dash in output; use a spaced double hyphen ` -- ` for asides. Write so a reader outside the project (or an AI issue generator) can act on each item without asking what it means.
 