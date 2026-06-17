---
name: do-work
description: Build the project from the GitHub Issues that make-issues created -- claim the next actionable issue, implement it on a branch, run the build gate, and open a pull request that closes it, following Mondo Robot's RFEF Lane 6 process. Use this skill whenever the user wants to work the backlog, build or implement the issues, pick up the next ticket, run the build loop, or ship the planned work -- and whenever a repo holds make-issues-managed issues and the user wants progress. Trigger it even if the user says "build the issues," "work the tickets," "start coding the plan," "do the next issue," "ralph the queue," or "run the overnight loop." It respects each issue's afk/hitl autonomy and never edits scope -- a build it cannot do as written escalates back to /make-tdd or /make-prd. Do NOT use it to author the PRD (use make-prd), design the TDD (use make-tdd), or create or sync the issues (use make-issues); this skill consumes those issues and writes code, PRs, and issue status.
---

# Do work

Build the project by executing the GitHub issues `make-issues` produced. The unit of work is one issue -- one thin, end-to-end slice. The doctrine that governs everything: **the PRD, the TDD, and the issues stay canonical; do-work consumes them and produces code, pull requests, and issue-status changes -- it never edits scope.** When a slice cannot be built as written, you stop and hand it back upstream rather than guess. This is RFEF Lane 6, the last lane -- `/make-prd` (the WHAT/WHY), `/make-tdd` (the HOW), and `/make-issues` (the work items) come first.

Like `make-issues`, this skill has **no local data file**. GitHub state is the record: the assignment, the labels, the closing PR, and the issue's open/closed status are how progress is tracked. And the version-lock chain extends here -- do-work refuses to build a backlog whose TDD has moved past the PRD, and refuses any single issue `make-issues` has already flagged stale.

## Execution model (the baseline for every run)

do-work runs as an **orchestrator plus workers** -- always, even for a single issue. The orchestrator (this session) does preflight, selection, dispatch, merge, and the report; it **never builds in its own context**. Each issue is built by a **worker** -- a fresh subagent handed only a pointer (the issue number and repo) that reads the issue and its TDD/PRD trace, builds on a branch, runs the gate, opens the PR, and returns a one-line verdict. The worker's heavy context (file reads, diffs, test logs) is discarded on return, so a run stays bounded however long the backlog is -- context compaction is a non-issue by design.

- **Default** -- orchestrator + one worker, then stop.
- **`--ralph`** -- a worker per issue across rounds, re-selecting after each (a merge unblocks the next tier), until the queue is dry or only HITL / blocked work remains.
- **Parallel (opt-in, 2-3)** -- when a round's issues are file-disjoint, dispatch 2-3 workers at once, each in its own **git worktree** (`isolation: worktree`) so they never clobber each other. Merges are always serial; the default is one worker at a time.

The mechanics (the worker brief, the verdict contract, worktrees, resuming) live in `references/execution-loop.md`; the deterministic drain is `workflows/drain-queue.js`.

## Flags (parse from the invocation)

- **default** -- build one issue this run, then stop at a **ready-for-review PR**; a human merges.
- **`--ralph`** -- drain the actionable AFK queue: after one issue, pick the next, until none are actionable or one needs a human.
- **`--auto-merge`** -- merge each PR once the build gate and required CI checks pass (the issue auto-closes COMPLETED), which unblocks its dependents, then continue. Pair with `--ralph` for the full overnight loop.
- **Invariant:** HITL issues are **never** auto-merged and **never** drained past. They always stop for a human, whatever the flags.

## Files in this skill

- `scripts/work_preflight.py` -- the read-only gate: auth, gh version, the PRD/TDD version lock, the repo, and that a backlog exists; plus advisories (flagged-stale issues, an owed sync, missing labels). Run it first, every run.
- `scripts/select_work.py` -- computes the actionable queue from the live issues: open, unflagged, unblocked, autonomy-matched, not in flight elsewhere; resumable-by-you first.
- `references/execution-loop.md` -- read before building: the orchestrator/worker split, the worker brief (claim, read, build, verify, PR), the verdict contract, worktrees and parallel rounds, and how a killed run resumes.
- `references/escalation-and-handback.md` -- read when a build is blocked: when to route to `/make-tdd` (a design gap) vs `/make-prd` (a wrong requirement) vs `/make-issues` (a stale issue), and how to write the hand-back so the upstream skill can act.
- `assets/pr-body-template.md` -- the PR body the build opens: the closing reference, the trace mirrored from the issue, the acceptance checklist, and how it was verified.
- `workflows/drain-queue.js` -- the deterministic drain (run via the Workflow tool): preflight, then a loop of select -> build workers -> serial auto-merge -> re-select until the queue is dry. The robust unattended path.

## Preflight (always, first action)

```
python scripts/work_preflight.py --prd prd-data.yaml --tdd tdd-data.yaml
```

**Both data files must be in the working tree** -- the lock needs both, same as `make-issues` (the TDD is often promoted into the repo while the PRD still lives in a Claude Project; bring a current `prd-data.yaml` in first). The gate checks, in order: `gh auth status`; **gh >= 2.94.0** (`brew upgrade gh` if older); the **version lock** (`prd-data.meta.prd_version` must equal `tdd-data.meta.prd_version` -- if not, the whole backlog is built against a moved PRD; stop and send the user to `/make-tdd` to re-lock, then `/make-issues` to sync); a git work tree with a resolvable `owner/name`; and that a **backlog exists** (no managed issues -> run `/make-issues` first).

It then prints non-gating **advisories**: open issues carrying `needs-rebase` / `spec-drift` / `orphaned` / `escalated` are **not buildable** until resolved; a possibly-owed `/make-issues` sync; and any missing do-work labels (`status:doing`, `escalated`) -- create them with `gh label create <name> --color <hex> --description "..." --force` before using them.

## Select the next work item

```
python scripts/select_work.py --repo <owner/name>                 # afk queue, next first
python scripts/select_work.py --repo <owner/name> --autonomy any --json
```

Actionable means: open, no not-buildable flag, **every blocker closed-completed**, autonomy matches the filter (default `afk`), and not in flight under someone else's name. An issue already assigned to you is **resumable** and sorts first, so an interrupted build is finished before a fresh one starts. Read `references/execution-loop.md`, then present the queue and the pick. In the default single-issue run, confirm the pick before building; under `--ralph`, proceed and report each issue in order.

## Build (the orchestrator dispatches a worker)

For each selected issue the orchestrator spawns a **worker subagent** -- it does not build in its own context, not even for one issue. The full worker brief and the verdict contract are in `references/execution-loop.md`. In a default single-issue run, confirm the pick first; under `--ralph`, proceed round by round. The invariants every worker holds:

- Build **only** the selected slice -- read the TDD capability by its `trace_tdd` ID (do not re-derive the design) and the `trace_prd` for the why; respect binding constraints (`BC-`).
- **No PR on a red build gate.** Open the PR with `Closes #N`, the trace mirrored from the issue meta, and the acceptance checklist; ready-for-review by default, merged only under `--auto-merge` once the gate and CI are green.
- **Never edit the `make-issues` managed regions** of the issue body (prose, meta, changelog). Progress is GitHub state: the assignment, the `status:doing` label, the PR, and comments. The TDD/PRD stay canonical.
- The worker returns a compact verdict (`built` / `escalated` / `failed`); the orchestrator records it, merges greens under `--auto-merge`, and re-selects.

## When to stop and hand back

Never edit the PRD, TDD, or an issue's scope to make a build pass. If you cannot satisfy the issue as written, stop and route upstream (`escalation-and-handback.md`):

- **A design gap or contradiction** (the HOW is wrong or missing) -> a build-blocker amend for `/make-tdd`.
- **An acceptance criterion that is itself wrong or unsatisfiable** (the WHAT) -> an `ESC-` escalation for `/make-prd`; a human validator decides, the skill only proposes.
- **An issue already flagged stale** (`needs-rebase` / `spec-drift` / `orphaned`) -> not yours to fix; `/make-issues` syncs it first.

Comment the reason on the issue, add the `escalated` label, and stop on that issue. The loop is forward-only: upstream amends, re-locks, and re-syncs; then you come back here.

## Report (every run)

Print the receipt: issues claimed; PRs opened (and merged, under `--auto-merge`); issues completed; anything flagged or escalated and why; what stays blocked and on which issue; and the remaining actionable queue. Under `--ralph`, report each issue in order and why the loop stopped.

## Honest limits

State these plainly; do not pretend past them.

- **Cannot self-trigger.** "Automatic" means a strong trigger description plus the cron/CI recipe below -- a genuine unattended run needs that wrapper, not the skill alone.
- **Dependencies are read from the issue body's Dependencies mirror.** GitHub does not expose native blocked-by edges through `gh ... --json` (the same limit `make-issues` documents). A hand-removed edge, or a mirror that disagrees with the native link, is not detected.
- **"Started" is inferred** (assignee + `status:doing` + closing PR). A hand-started branch with no closing PR reads as not-started.
- **Builds only current work.** It trusts `make-issues` for drift detection (the flags) and refuses flagged issues; it does not recompute fingerprints.
- **Parallel needs disjoint slices.** Worktrees stop parallel workers from clobbering each other's tree, but two issues that touch the same file still conflict at merge, and under `--auto-merge` later same-round PRs may need a rebase. Keep parallel to 2-3 file-disjoint issues; otherwise run serial. Worktrees that committed work may need pruning (`git worktree prune`) after their branches merge.
- **No locking.** A run killed mid-build leaves a branch and an assignment; re-running resumes the issue already assigned to you, because selection puts resumable issues first. The attempted-set prevents re-processing within a drain.

## Automation (cron / CI)

do-work runs unattended only when something invokes it. Two paths:

- **Headless skill call** -- `claude -p "/do-work --ralph --auto-merge"` from inside the repo (a cron job, or CI on a schedule or on issue events). The orchestrator drains the AFK queue and stops at the first thing that needs a human. Good for a handful of issues.
- **The drain workflow** -- for a long backlog, run `workflows/drain-queue.js` via the Workflow tool:
  ```
  Workflow({ scriptPath: "<do-work>/workflows/drain-queue.js",
             args: { repo: "owner/name", skillDir: "<do-work>",
                     autoMerge: true, parallel: 2 } })
  ```
  It encodes the same select -> build -> merge -> re-select loop deterministically, keeps each build in a fresh worker, and returns a structured run summary. The durable drain path. (The Workflow tool requires explicit opt-in.)

Either way: grant the run the permissions the build needs (edit files, run the repo's test/build commands, and `gh`/`git`); HITL issues are never auto-built or auto-merged; keep a human reviewing the merged PRs -- the loop ships work, it does not own the product.

## Tone and writing rules

Plain words, short sentences, no marketing language. State what you built and how you proved it. Never use an em dash in output; use a spaced double hyphen ` -- ` for asides. Write so the next agent, or the human reviewing the PR, can see what was done without asking.
