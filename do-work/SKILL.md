---
name: do-work
description: Build the project from the GitHub Issues that make-issues created -- claim the next actionable issue, implement it on a branch, run the build gate, and open a pull request that closes it, following Mondo Robot's RFEF Lane 6 process. Use this skill whenever the user wants to work the backlog, build or implement the issues, pick up the next ticket, run the build loop, or ship the planned work -- and whenever a repo holds make-issues-managed issues and the user wants progress. Trigger it even if the user says "build the issues," "work the tickets," "start coding the plan," "do the next issue," "ralph the queue," or "run the overnight loop." It respects each issue's afk/hitl autonomy and never edits scope -- a build it cannot do as written escalates back to /make-tdd or /make-prd. Do NOT use it to author the PRD (use make-prd), design the TDD (use make-tdd), or create or sync the issues (use make-issues); this skill consumes those issues and writes code, PRs, and issue status.
---

# Do work

Build the project by executing the GitHub issues `make-issues` produced. The unit of work is one issue -- one thin, end-to-end slice. The doctrine that governs everything: **the PRD, the TDD, and the issues stay canonical; do-work consumes them and produces code, pull requests, and issue-status changes -- it never edits scope.** When a slice cannot be built as written, you stop and hand it back upstream rather than guess. This is RFEF Lane 6, the last lane -- `/make-prd` (the WHAT/WHY), `/make-tdd` (the HOW), and `/make-issues` (the work items) come first.

Like `make-issues`, this skill has **no local data file**. GitHub state is the record: the assignment, the labels, the closing PR, and the issue's open/closed status are how progress is tracked. And the version-lock chain extends here -- do-work refuses to build a backlog whose TDD has moved past the PRD, and refuses any single issue `make-issues` has already flagged stale.

## Execution model (the baseline for every run)

do-work runs as an **orchestrator plus workers** -- always, even for a single issue. The orchestrator (this session) does preflight, selection, dispatch, merge, and the report; it **never builds in its own context**. Each issue is built by a **worker** -- a fresh subagent handed only a pointer (the issue number and repo) that reads the issue and its TDD/PRD trace, builds on a branch, runs the gate, opens the PR, and returns a one-line verdict. The worker's heavy context (file reads, diffs, test logs) is discarded on return, so a run stays bounded however long the backlog is -- context compaction is a non-issue by design.

- **Default** -- drain the whole actionable queue: a worker per issue across rounds, re-selecting after each (a merge unblocks the next tier), until the queue is dry or only HITL / blocked work remains.
- **`--limit=<N>`** -- stop after N issues this run (`--limit=1` builds a single issue, the old default).
- **Parallel (opt-in, 2-3)** -- when a round's issues are file-disjoint, dispatch 2-3 workers at once, each in its own **git worktree** (`isolation: worktree`) so they never clobber each other. Merges are always serial; the default is one worker at a time.

Every built PR then runs through a **review -> fix loop**: `do-pr-review` posts inline findings, `do-pr-fix` addresses them and replies in-thread, and a re-review repeats until no Critical/Major findings remain (max `maxReviewRounds`, default 2). This happens on every run; merge stays manual unless `--auto-merge`.

The mechanics (the worker brief, the verdict contract, the review/merge gate, worktrees, resuming) live in `references/execution-loop.md`; the deterministic drain is `workflows/drain-queue.js`.

## Flags (parse from the invocation)

- **default** -- drain the whole actionable AFK queue: build each issue, **review and fix** its PR, then re-select until none are actionable or only HITL / blocked work remains. Clean PRs are left **ready-for-review**; a human merges.
- **`--limit=<N>`** -- cap the run at N issues processed (`--limit=1` builds a single issue then stops; `--limit=0` or omitted = unlimited).
- **`--phase=<N>`** -- drain only issues in implementation phase N -- the GitHub milestone `Phase N: ...` that `make-issues` created from the TDD's implementation plan. Composes with `--limit`; omitted = all phases. An issue with no phase milestone (or a non-`Phase N:` one) is skipped and reported. The dependency gate still applies, so a phase-N issue whose blocker is an unmerged earlier-phase issue stays excluded until that blocker merges -- to drain a phase end-to-end in one pass, add `--auto-merge`.
- **`--issue=<N>`** -- build exactly issue N, then stop. It bypasses the phase and autonomy queue filters (you picked it explicitly), but still honors the not-buildable gates: a flagged (`needs-rebase`/`spec-drift`/`orphaned`/`escalated`), blocked, or in-flight-elsewhere target is reported with its reason rather than built. Takes precedence over `--phase`. HITL is still never auto-merged.
- **`--auto-merge`** -- once a PR's review loop comes back clean and required CI checks pass, merge it (the issue auto-closes COMPLETED), which unblocks its dependents, then continue. The full overnight loop. The merge agent reports each PR accepted and merged back to the orchestrator.
- **`--dangerously`** -- **full autonomy, accept the risk.** Build **and merge every** buildable issue (AFK **and** HITL), and **never stop for a human**. It forces `--autonomy any` + auto-merge, and flips three gates (see *Dangerous mode* below): build HITL and merge it; **resolve** implementation gaps with best-practice defaults and **mock** missing externals instead of escalating; and **merge on green CI even with unresolved review findings**. Everything it decides on its own is opened as a `needs-human-review` **follow-up issue**. A **red CI is never merged** (it would break the default branch) -- it is flagged and left open. Composes with `--phase`/`--limit`/`--issue`. Still skips make-issues stale/escalated issues.
- **`--ralph`** -- deprecated no-op; draining is now the default.
- **Invariant:** HITL issues are **never** auto-merged and **never** drained past -- they always stop for a human -- **except under `--dangerously`**, which builds and merges them like any other.

## Files in this skill

- `scripts/work_preflight.py` -- the read-only gate: auth, gh version, the PRD/TDD version lock, the repo, and that a backlog exists; plus advisories (flagged-stale issues, an owed sync, missing labels). Run it first, every run.
- `scripts/select_work.py` -- computes the actionable queue from the live issues: open, unflagged, unblocked, autonomy-matched, not in flight elsewhere; resumable-by-you first.
- `references/execution-loop.md` -- read before building: the orchestrator/worker split, the worker brief (claim, read, build, verify, PR), the verdict contract, worktrees and parallel rounds, and how a killed run resumes.
- `references/escalation-and-handback.md` -- read when a build is blocked: when to route to `/make-tdd` (a design gap) vs `/make-prd` (a wrong requirement) vs `/make-issues` (a stale issue), and how to write the hand-back so the upstream skill can act.
- `assets/pr-body-template.md` -- the PR body the build opens: the closing reference, the trace mirrored from the issue, the acceptance checklist, and how it was verified.
- `workflows/drain-queue.js` -- the deterministic drain (run via the Workflow tool): preflight, then a loop of select -> build workers -> review -> fix loop -> serial auto-merge -> re-select until the queue is dry. The robust unattended path.

## Preflight (always, first action)

```
python scripts/work_preflight.py --prd prd-data.yaml --tdd tdd-data.yaml
```

**Both data files must be in the working tree** -- the lock needs both, same as `make-issues` (the TDD is often promoted into the repo while the PRD still lives in a Claude Project; bring a current `prd-data.yaml` in first). The gate checks, in order: `gh auth status`; **gh >= 2.94.0** (`brew upgrade gh` if older); the **version lock** (`prd-data.meta.prd_version` must equal `tdd-data.meta.prd_version` -- if not, the whole backlog is built against a moved PRD; stop and send the user to `/make-tdd` to re-lock, then `/make-issues` to sync); a git work tree with a resolvable `owner/name`; and that a **backlog exists** (no managed issues -> run `/make-issues` first).

It then prints non-gating **advisories**: open issues carrying `needs-rebase` / `spec-drift` / `orphaned` / `escalated` are **not buildable** until resolved; a possibly-owed `/make-issues` sync; and any missing do-work labels (`status:doing`, `escalated`, and `needs-human-review` -- the last is applied to the follow-up issues `--dangerously` opens) -- create them with `gh label create <name> --color <hex> --description "..." --force` before using them.

## Select the next work item

```
python scripts/select_work.py --repo <owner/name>                 # afk queue, next first
python scripts/select_work.py --repo <owner/name> --autonomy any --json
python scripts/select_work.py --repo <owner/name> --phase 1        # only phase 1
python scripts/select_work.py --repo <owner/name> --issue 42       # just issue #42
```

Actionable means: open, no not-buildable flag, **every blocker closed-completed**, autonomy matches the filter (default `afk`), the phase matches when `--phase` is set, and not in flight under someone else's name. An issue already assigned to you is **resumable** and sorts first, so an interrupted build is finished before a fresh one starts. `--issue=N` narrows to that one issue and skips the autonomy/phase filters but keeps the buildable gates (so it reports, rather than builds, a flagged or blocked target). Read `references/execution-loop.md`, then present the queue and the pick. With `--limit=1` or `--issue`, confirm the pick before building; otherwise proceed round by round and report each issue in order.

## Build (the orchestrator dispatches a worker)

For each selected issue the orchestrator spawns a **worker subagent** -- it does not build in its own context, not even for one issue. The full worker brief and the verdict contract are in `references/execution-loop.md`. With `--limit=1`, confirm the pick first; otherwise proceed round by round. The invariants every worker holds:

- Build **only** the selected slice -- read the TDD capability by its `trace_tdd` ID (do not re-derive the design) and the `trace_prd` for the why; respect binding constraints (`BC-`).
- **No PR on a red build gate.** Open the PR with `Closes #N`, the trace mirrored from the issue meta, and the acceptance checklist; ready-for-review by default, merged only under `--auto-merge` once the gate and CI are green.
- **Never edit the `make-issues` managed regions** of the issue body (prose, meta, changelog). Progress is GitHub state: the assignment, the `status:doing` label, the PR, and comments. The TDD/PRD stay canonical.
- The worker returns a compact verdict (`built` / `escalated` / `failed`); the orchestrator records it, runs the **review -> fix loop** on each built PR, merges clean greens under `--auto-merge`, and re-selects.

## When to stop and hand back

Never edit the PRD, TDD, or an issue's scope to make a build pass. If you cannot satisfy the issue as written, stop and route upstream (`escalation-and-handback.md`):

- **A design gap or contradiction** (the HOW is wrong or missing) -> a build-blocker amend for `/make-tdd`.
- **An acceptance criterion that is itself wrong or unsatisfiable** (the WHAT) -> an `ESC-` escalation for `/make-prd`; a human validator decides, the skill only proposes.
- **An issue already flagged stale** (`needs-rebase` / `spec-drift` / `orphaned`) -> not yours to fix; `/make-issues` syncs it first.

Comment the reason on the issue, add the `escalated` label, and stop on that issue. The loop is forward-only: upstream amends, re-locks, and re-syncs; then you come back here.

## Dangerous mode (`--dangerously`)

`--dangerously` is the opt-in override of the cautious defaults above, for when the operator wants maximum throughput and **owns the risk**. It runs the whole loop -- build, review, fix, **merge** -- over **every** buildable issue (AFK **and** HITL) and **never prompts a human**. It changes the *terminal decisions*, not the machinery: the build gate, the review->fix loop, worktrees, and the orchestrator/worker split are unchanged. Three flips:

- **HITL is built and merged** like any other issue (the only run where the HITL invariant is lifted).
- **Resolve, don't escalate.** What would normally escalate-and-stop is instead resolved: pick the **best-practice default** for an ambiguous or unsatisfiable criterion; **mock/placeholder** a missing external (an API, seed data, a credential) with a clearly-marked `FIXME(dangerously)` stub so the gate passes against the mock. You still **never edit the PRD/TDD or an issue's managed scope** -- you resolve *implementation* ambiguity and mock *missing externals*, you do not rewrite requirements.
- **Merge on green CI even with unresolved review findings.** The review->fix loop still runs; if it can't converge, the residual findings are flagged and the PR is **merged anyway** on green CI. A **red CI is never merged** -- it is flagged and left open.

Everything decided on its own is opened as a **`needs-human-review` follow-up issue** (title `Follow-up: <what> on #N`, body = what was assumed/mocked/left-unresolved and where), linked from a PR comment, so a human can triage the debt later. Follow-ups are deliberately *not* `make-issues`-managed, so the loop never re-builds its own mocks. It still **skips** make-issues stale/`escalated` issues -- a known-stale spec is the one thing dangerous mode does not power through; run `/make-issues` to sync first.

The robust path for a real dangerous run is the drain workflow with `dangerously: true`, or `claude -p "/do-work --dangerously"`.

## Report (every run)

Print the receipt: issues claimed; PRs opened, reviewed, and fixed (and merged, under `--auto-merge`); issues completed; any PR parked for a human because the review loop could not converge; anything flagged or escalated and why; what stays blocked and on which issue; and the remaining actionable queue. Report each issue in order, its review outcome (clean, or parked after N rounds), and why the loop stopped. Under `--dangerously`, also list every `needs-human-review` follow-up opened (assumptions, mocks, findings merged anyway, red-CI skips) -- that list is the human's triage queue.

## Honest limits

State these plainly; do not pretend past them.

- **Cannot self-trigger.** "Automatic" means a strong trigger description plus the cron/CI recipe below -- a genuine unattended run needs that wrapper, not the skill alone.
- **Dependencies are read from the issue body's Dependencies mirror.** GitHub does not expose native blocked-by edges through `gh ... --json` (the same limit `make-issues` documents). A hand-removed edge, or a mirror that disagrees with the native link, is not detected.
- **"Started" is inferred** (assignee + `status:doing` + closing PR). A hand-started branch with no closing PR reads as not-started.
- **Builds only current work.** It trusts `make-issues` for drift detection (the flags) and refuses flagged issues; it does not recompute fingerprints.
- **Parallel needs disjoint slices.** Worktrees stop parallel workers from clobbering each other's tree, but two issues that touch the same file still conflict at merge, and under `--auto-merge` later same-round PRs may need a rebase. Keep parallel to 2-3 file-disjoint issues; otherwise run serial. Worktrees that committed work may need pruning (`git worktree prune`) after their branches merge.
- **No locking.** A run killed mid-build leaves a branch and an assignment; re-running resumes the issue already assigned to you, because selection puts resumable issues first. The attempted-set prevents re-processing within a drain.
- **Review runs as the same gh identity.** Builder, reviewer, and fixer authenticate as the same user, so the in-loop review **cannot post a formal `REQUEST_CHANGES`** (GitHub forbids it on your own PR). The merge gate runs off the reviewer's **structured verdict** -- the count of open Critical/Major findings -- not GitHub's review state; the fixer is told to act on the reviewer's same-user threads and always reply in-thread. A separate review identity (a bot token) would let GitHub's review state carry the signal natively.
- **Default drains only the unblocked tier.** Dependent issues unblock only when their blockers **merge**, and nothing merges without `--auto-merge` -- so a default run produces a stack of reviewed, ready-to-merge PRs for the independent front. Draining a full dependency chain in one pass needs `--auto-merge`. The same applies to `--phase`: a phase only fully drains in one pass when its cross-phase blockers are already merged or `--auto-merge` is on.
- **Phase comes from the milestone, not the issue body.** `--phase=N` reads each issue's GitHub milestone (`Phase N: ...`), which `make-issues` sets from the TDD's implementation plan. An issue with no milestone or a non-conforming title is treated as phase-less and excluded from a `--phase` run; a repo whose TDD has no plan has no phase milestones, so `--phase` matches nothing. Run `/make-issues` to (re)assign milestones after the plan changes.
- **`--dangerously` trades safety for throughput, by design.** It can merge code that still has unresolved Critical/Major review findings (on green CI), and it merges HITL work -- visual/brand judgments, security or data-migration sign-offs, anything touching production data or money -- with **no human in the loop before the merge**. Its mocks/placeholders are real code that ships behind a `needs-human-review` follow-up, not something that blocks the merge. Use it only when the operator owns that risk and a human will work the follow-up queue afterward. It still cannot reach a known-stale spec (make-issues drift/`escalated` issues are skipped) and it never merges a red CI.

## Automation (cron / CI)

do-work runs unattended only when something invokes it. Two paths:

- **Headless skill call** -- `claude -p "/do-work --auto-merge"` from inside the repo (a cron job, or CI on a schedule or on issue events). The orchestrator drains the AFK queue, reviews and fixes each PR, and stops at the first thing that needs a human. Good for a handful of issues.
- **The drain workflow** -- for a long backlog, run `workflows/drain-queue.js` via the Workflow tool:
  ```
  Workflow({ scriptPath: "<do-work>/workflows/drain-queue.js",
             args: { repo: "owner/name", skillDir: "<do-work>",
                     autoMerge: true, limit: 0, maxReviewRounds: 2, parallel: 2 } })
  ```
  It encodes the same select -> build -> review -> fix -> merge -> re-select loop deterministically, keeps each build, review, and fix in a fresh worker, and returns a structured run summary (built, merged, parked-for-review, escalated, failed). Add `phase: <N>` to drain a single implementation phase, or `issue: <N>` to build one targeted issue. Add `dangerously: true` for full autonomy -- it forces `autonomy: 'any'` + `autoMerge`, builds and merges HITL, resolves/mocks instead of escalating, merges on green CI even with open findings, opens `needs-human-review` follow-ups, and lists them in the run summary. It locates `do-pr-review` and `do-pr-fix` as siblings of `skillDir` by default (override with `reviewSkillDir` / `fixSkillDir`). The durable drain path. (The Workflow tool requires explicit opt-in.)
  - **Per-stage models.** Each stage runs on a fitted model by default -- build and review on **Opus**, fix on **Sonnet**, the mechanical steps (preflight/select/escalate/merge) on **Haiku** -- overridable per run via `model<Stage>` / `effort<Stage>` args (`modelBuild`, `modelReview`, `modelFix`, `effortBuild`, `effortReview`, `effortFix`, etc.). Note: if the `CLAUDE_CODE_SUBAGENT_MODEL` env var is set it overrides all of these, so leave it unset in CI/cron.

Either way: grant the run the permissions the build needs (edit files, run the repo's test/build commands, and `gh`/`git`); HITL issues are never auto-built or auto-merged **unless `--dangerously` is set**; keep a human reviewing the merged PRs -- the loop ships work, it does not own the product. Under `--dangerously`, that human review happens *after* the merge, via the `needs-human-review` follow-up queue.

## Tone and writing rules

Plain words, short sentences, no marketing language. State what you built and how you proved it. Never use an em dash in output; use a spaced double hyphen ` -- ` for asides. Write so the next agent, or the human reviewing the PR, can see what was done without asking.
