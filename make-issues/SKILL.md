---
name: make-issues
description: Turn an approved, version-locked PRD and TDD into traceable GitHub Issues, and keep those issues in sync as the TDD changes, using Mondo Robot's RFEF Lane 4 process. Use this skill whenever the user wants to generate issues or tickets from a TDD, break the design into work items, push the plan to GitHub, or reconcile existing issues after a TDD update. Trigger it even if the user says "create the tickets," "make the issues," "plan the work," "break this down," or "sync the issues with the latest TDD." Do NOT use for authoring the PRD (upstream -- use make-prd) or the TDD (upstream -- use make-tdd); this skill consumes both and writes to GitHub.
---

# Make issues

Turn an approved, version-locked PRD and TDD into GitHub Issues that humans and coding agents can act on, then keep those issues honest as the TDD changes. The job is **traceability and stale-resistance**, not just decomposition. This is the last lane in the chain -- `/make-prd` (the WHAT/WHY) and `/make-tdd` (the HOW) come first; when the TDD later changes, you return here to sync.

Unlike `make-prd` and `make-tdd`, this skill has **no local data file and no validator**. The output is GitHub state: the issues, their trace labels, and a machine-readable meta block embedded in each issue body ARE the index. You query them live with `gh ... --json`. The check that stands in for a validator is a coverage/reconciliation **report**, printed every run.

The doctrine that governs everything: **the TDD stays canonical; an issue is a derived projection.** To change scope you change the TDD and re-sync -- you never edit the requirement inside an issue. Every issue traces to the TDD capability and PRD requirement it serves and stamps the document versions it was born from; no issue without a trace. Engineers may still add notes in the issue's human region, which sync never overwrites.

This skill has two modes. Decide which one applies before doing anything else:

- **Generate mode** -- no skill-managed issues exist yet. Input is the PRD + TDD; output is the full work-item set, created in GitHub.
- **Sync mode** -- managed issues exist. Input is a changed TDD. Output is a reconciliation: update, flag, follow-up, or close, per issue. Generate is Sync run against an empty set; they share one engine.

## Files in this skill

- `assets/issue-body-template.md` -- the issue body: managed regions (the prose, the `meta` block, the `changelog`) plus a `human` region sync never overwrites. Read it before creating issues; follow the authoring comments, then strip them.
- `assets/labels.yaml` -- the label scheme (provenance, autonomy, reconciliation flags) and the meta-block contract. Labels stay human-facing; traceability and source versions are carried in the issue body, not as labels. Read it before ensuring labels or writing the meta block.
- `references/slicing-and-review.md` -- read in Generate mode and for new items in Sync: how to cut the TDD into thin work items, mark AFK/HITL, assemble trace fields, and run the review gate before any write.
- `references/reconciliation.md` -- read in Sync mode: the match maps, state detection, the decision tree, the managed-region surgery, and the report.
- `scripts/gh_preflight.py` -- the preflight gate (read-only): auth, gh version, repo, the version-lock gate, mode, and missing labels. Run it first, every run.
- `scripts/item_fingerprint.py` -- per-capability fingerprint over the contract-bearing TDD fields; the hash stamped on each issue and compared on sync.
- `scripts/phase_milestones.py` -- maps the TDD's `implementation_phases` to GitHub milestones (capability -> phase, phase -> milestone title) and, with `--ensure`, creates/patches them. Used only when the TDD has a plan.

## Preflight (always, first action)

Run the gate and stop on any failure before touching GitHub:

```
python scripts/gh_preflight.py --prd prd-data.yaml --tdd tdd-data.yaml
```

**Both data files must be in the working tree.** The TDD is often promoted into the repo while the PRD still lives in a Claude Project (see make-tdd, *Location & system of record*). If only `tdd-data.yaml` is here, the lock cannot be verified -- you can read the TDD's locked version but not whether the live PRD has moved past it. Bring a current `prd-data.yaml` (the version the TDD is locked to) into the tree first; preflight fails fatally and says so if either file is missing.

It checks, in order: `gh auth status`; **gh >= 2.94.0** (native dependency/type flags -- below that, stop and tell the user to `brew upgrade gh`); a git work tree with a resolvable `owner/name` (confirm the target before any write); the **version-lock gate** (`prd-data.meta.prd_version` must equal `tdd-data.meta.prd_version` -- if not, the TDD is stale; stop and send the user to `/make-tdd` to re-lock); and the existing managed issues, which pick the mode. It reports any missing static labels; create them with `gh label create <name> --color <hex> --description "..." --force` from `assets/labels.yaml`. That static set is the whole scheme -- there are no per-run dynamic labels. Traceability and source versions both live in the issue body (the `## Traceability` table and the meta block), never as labels.

It also prints an **approval advisory** (non-gating): the lock can pass while both docs are still `draft`. If preflight warns that the PRD or TDD is not `approved`, surface that and get explicit confirmation before creating anything -- issues built on a draft will churn when it lands. This mirrors make-tdd's warn-don't-block posture; only a human approves a doc.

The version lock is what lets this skill reason about a single drift axis. Because the TDD already matches the PRD, you only ever reconcile TDD capability vs. issue -- never PRD vs. issue.

## Mode selection

No managed issues -> **Generate**. Managed issues exist -> **Sync**. Both run the same reconciliation engine; Generate is the empty-set case. Read the matching reference before acting.

## Generate mode workflow

1. **Read both sources.** `tdd-data.yaml` (the capabilities, traceability, binding constraints, and `implementation_phases` if present) and `prd-data.yaml` (objectives, success criteria). Read `references/slicing-and-review.md` now.
2. **Slice thin.** Cut active capabilities into independently-completable, end-to-end work items; prefer many thin slices to few thick ones; mark each AFK or HITL, preferring AFK.
3. **Assemble each item.** Goal + success criteria from the PRD; what-to-build + test plan + NFRs from the TDD; `trace_tdd` + `trace_prd`; `source_versions` from the two `meta` blocks; `fingerprint` from `item_fingerprint.py --id <CAP>`. No item without a trace. When the TDD has a plan, also note each item's phase from `phase_milestones.py` (carried by the milestone, not the body).
4. **Review pass (the human gate).** Present the breakdown -- grouped by phase when the TDD has a plan (per item: title, AFK/HITL, blocked-by, trace IDs) -- plus the coverage check (capabilities, requirements, and phases). Iterate to approval. Create nothing first.
5. **Create in dependency order**, blockers first, so each `--blocked-by` references a real issue number. When the TDD has a plan, first ensure the milestones exist (`phase_milestones.py --ensure --repo <owner/name>`), then assign each issue its phase milestone (`gh issue create ... --milestone "Phase <N>: <name>"`). Stamp every issue per the template and apply its labels.

## Sync mode workflow

1. **Read `references/reconciliation.md`** and pull the managed issues with the `--json` field set it lists.
2. **Build the maps:** issue-by-capability (match on the meta block's `trace_tdd`; a missing or malformed block is not auto-recovered -- flag it for a human, who reads the capability ID from the body's `## Traceability` table and re-stamps the block) and capability-to-fingerprint (`item_fingerprint.py`).
3. **Detect each issue's state** (not-started / started / completed / won't-do / orphan) and **apply the decision tree:** skip unchanged; auto-update not-started; comment-and-flag started; follow-up completed; close or flag orphans.
4. **Auto-update touches only the managed regions** -- the human region is spliced back byte-for-byte, with asserts that abort to comment-and-flag if the markers were hand-edited.
5. **Re-assert phase milestones** (when the TDD has a plan) -- a separate axis from the fingerprint decision tree, run every sync: ensure the milestones exist, then re-assign any issue whose phase moved, silently and without a flag (a re-sequence is not a scope change). See `references/reconciliation.md` §6.
6. **Present the reconciliation plan for approval** before writing, then execute and print the report.

## Report (every run)

Always print the receipt: coverage (every active capability has an issue, or the gap is named), traceability (every issue resolves to a current capability with PRD trace and both versions), DAG integrity (the desired dependency graph is acyclic, or the cycle is named), the lock (asserted in preflight), and drift (every changed capability accounted for by an action). When the TDD has a plan, also report phase coverage (every active phase has an issue; every issue has a milestone) and any phase-spanning issue. Summarize counts: created, updated, flagged, closed, follow-ups, skipped; and, with a plan, milestones created/updated and issues re-assigned to a new phase.

## Honest limits

State these plainly; do not pretend past them.

- **Native dependencies need gh >= 2.94.0.** The `--blocked-by`/`--blocking`/`--type`/`--parent` flags do not exist below that. Preflight hard-gates it.
- **Dependencies are write-only.** GitHub dependency edges cannot be read back via `gh ... --json`. Reconciliation works from the desired DAG derived from the TDD, cycle-checks it, and re-asserts edges idempotently; it does not diff live edges or detect a human-removed one.
- **"Started" is inferred.** GitHub has no native in-progress state, so it is read from assignee + closing-PR. A hand-started branch with no closing PR reads as not-started.
- **No locking, no atomic multi-issue transaction.** A sync is a sequence of `gh` calls; a process killed mid-run leaves some issues updated. Re-running reconciles it, because every action is keyed on fingerprint equality.
- **Milestones are repo-global.** Phase milestones (`Phase N: name`) live at the repo level, not scoped to a project -- one project per repo is the assumption. An issue whose `trace_tdd` spans phases is filed under the **latest** and reported as a slicing smell; phase grouping is only as clean as the slicing. The phase axis is re-asserted every sync but, like dependency edges, a human-removed milestone is silently restored, not detected as drift.

## Tone and writing rules for issues

Plain words, short sentences, no marketing language. State each work item as one thin slice with checkable acceptance criteria. Never use an em dash in output; use a spaced double hyphen ` -- ` for asides. Write so a coding agent can act on each issue without asking what it means.
