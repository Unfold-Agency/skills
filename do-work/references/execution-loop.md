# Execution Loop

How do-work turns make-issues work items into closing pull requests. The prime directive: **the orchestrator never builds; a fresh worker builds each issue in its own context.** This split is the baseline for *every* run -- a single-issue run is the orchestrator plus one worker; a drain is the orchestrator plus many. It is what keeps the run's context bounded no matter how long the backlog is: the heavy work (file reads, diffs, test logs) lives and dies inside each worker, and the orchestrator only ever holds the queue and a one-line verdict per issue.

## Two roles

| Role | Context holds | Job |
|---|---|---|
| **Orchestrator** (the do-work session) | the queue + one verdict per issue | preflight once, select, dispatch workers, merge, re-select, report |
| **Worker** (one per issue, isolated) | the whole build for one issue | claim, read, build, verify, open the PR, return a verdict |

A worker gets a **pointer** -- the issue number and repo -- not shared context. Everything it needs is reachable from there (the issue, its `trace_tdd`/`trace_prd`, the TDD capability, the PRD), which is exactly why make-issues slices each item to be completable in one agent loop. When the worker returns, its context is discarded; the orchestrator keeps only the verdict.

## The orchestrator's job

1. **Preflight once** (`work_preflight.py`). Ensure the lifecycle labels exist (`status:doing`, `escalated`). Stop on any gating failure.
2. **Select** (`select_work.py --autonomy afk`). This is the actionable queue: open, unflagged, unblocked, autonomy-matched, not in flight elsewhere -- resumable-by-you first.
3. **Dispatch a worker per issue.** Spawn a subagent with the worker brief below (the do-work session does this with its Task/subagent tool; the bundled `workflows/drain-queue.js` does it with `agent()`). Do **not** build in the orchestrator's own context -- not even for a single issue. That is the rule.
4. **Collect the verdict** (the contract below). Record it; do not absorb the worker's transcript.
5. **Merge** (only under `--auto-merge`, and only for `built` verdicts): merge each green PR **serially** (autonomy + CI guards in the merge step). A merge closes the issue COMPLETED and unblocks its dependents.
6. **Re-select and repeat** under `--ralph`: a fresh `select_work.py` pass surfaces issues a merge just unblocked. Keep an **attempted set** -- never re-dispatch an issue already tried this run -- so the loop terminates instead of rebuilding the same item. Stop when the queue is dry, or when only HITL / blocked / flagged items remain. Without `--ralph`, do one issue and stop.
7. **Report** (every run): built, merged, escalated, failed, still-blocked, and the remaining queue.

## The worker's job (one issue)

This is the brief a worker runs. Build **only** the one slice; do not widen scope or touch another issue.

1. **Claim it** -- `gh issue edit <N> --repo <owner/name> --add-assignee @me --add-label status:doing`. If it is already yours (a resumed run), continue from the branch rather than restarting.
2. **Read, in order** -- the issue (`gh issue view <N>`: Goal, What to build, Acceptance criteria, Test plan, and the `make-issues:meta` block); the TDD capability the `trace_tdd` IDs point at (in `tdd-data.yaml` / `TDD.md` -- do not re-derive it); the `trace_prd` requirement for the why. Honor any binding constraints (`BC-`) the capability is `bounded_by`. If the issue cannot be built as written, escalate (below) instead of coding around it.
3. **Build on a branch** -- `git switch -c <type>/issue-<N>-<short-slug>` off the default branch, following `git-workflow` (emoji-first Conventional Commits, one logical change per commit). Implement this slice only.
4. **Verify -- the build gate** -- detect and run what the repo has (check `package.json` scripts, `Makefile`, `pyproject.toml`, CI config, the repo `CLAUDE.md`): tests, then build, then lint, plus the issue's Test plan. **No PR on a red gate.** Fix it if it is your slice's doing; otherwise escalate or return `failed`.
5. **Open the PR** -- `git push -u origin <branch>`, then fill `assets/pr-body-template.md` and `gh pr create`: `Closes #<N>` (the merge closes the issue COMPLETED and the link populates), the trace mirrored from the issue meta, the acceptance checklist, and how it was verified. **Ready-for-review by default** (draft only to park an HITL decision).
6. **Status is GitHub state** -- the assignment, `status:doing`, the PR, and issue comments. **Never edit the make-issues managed regions** of the issue body (prose, `meta`, changelog). Track acceptance in the PR, not by ticking the issue's boxes.
7. **Return the verdict** and stop.

## The worker result contract

The worker returns this and nothing else -- it is the entire handoff back to the orchestrator:

```yaml
issue:   <number>
status:  built | escalated | failed
branch:  <branch name, when built>
pr_url:  <PR URL, when built>
gate:    <e.g. "tests+lint pass">
summary: <one line>
```

- **built** -- PR open (and green), ready to merge.
- **escalated** -- could not be built as written; the worker has commented the reason and added the `escalated` label (so the next select excludes it). The orchestrator routes it per `escalation-and-handback.md`; it never silently retries.
- **failed** -- the gate stayed red for a reason that is not an escalation. The orchestrator records it and the attempted-set keeps the loop from re-trying it this run.

## Serial by default, parallel by round

- **Serial (the baseline)** -- one worker at a time, in the main working tree. This already bounds context fully and is always safe.
- **Parallel (2-3, opt-in)** -- dispatch a round of workers **only when their issues are file-disjoint** (different areas of the tree). Each parallel worker runs in its **own git worktree** (`isolation: worktree`) so their uncommitted changes never collide; the worktree is removed automatically if a worker makes no change. Keep it to 2-3.
- **Caveats that keep parallel honest:** under `--auto-merge`, each merge moves the default branch, so later same-round PRs may need a rebase -- and two "independent" issues that touch the same file still conflict at PR/merge time. When unsure whether a batch is disjoint, run it serially. **Merges are always serial**, never concurrent.

## Resuming a killed run

A run killed mid-build leaves a branch and an assignment. Because `select_work.py` sorts resumable (already-yours) issues first, the next run picks the half-built issue back up. The resuming worker reconciles branch state first -- pull, re-run the gate -- rather than starting over.

## Draining the whole backlog

For an unattended drain, the orchestration above is encoded deterministically in `workflows/drain-queue.js` (run via the Workflow tool): preflight, then a loop of select -> parallel build workers -> serial auto-merge -> re-select, until the queue is dry. It takes `args.repo` and `args.skillDir`, plus `autoMerge`, `parallel` (1-3), and `maxIssues`. The script holds the loop and the verdicts; each build is still a fresh worker. See SKILL.md, *Execution model*.
