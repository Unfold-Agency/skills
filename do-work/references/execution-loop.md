# Execution Loop

How do-work turns make-issues work items into closing pull requests. The prime directive: **the orchestrator never builds; a fresh worker builds each issue in its own context.** This split is the baseline for *every* run -- a single-issue run is the orchestrator plus one worker; a drain is the orchestrator plus many. It is what keeps the run's context bounded no matter how long the backlog is: the heavy work (file reads, diffs, test logs) lives and dies inside each worker, and the orchestrator only ever holds the queue and a one-line verdict per issue.

## Two roles

| Role | Context holds | Job |
|---|---|---|
| **Orchestrator** (the do-work session) | the queue + one verdict per issue | preflight once, select, dispatch workers, merge, re-select, report |
| **Worker** (one per issue, isolated) | the whole build for one issue | claim, read, build, verify, open the PR, return a verdict |

A worker gets a **pointer** -- the issue number and repo -- not shared context. Everything it needs is reachable from there: the issue is **self-contained** (it embeds the requirement, its EARS acceptance criteria, and a governing-ADR snippet) and carries `trace_req`/`trace_adr`/`feature` plus the ADRs in `docs/specs/decisions/`, which is exactly why make-issues slices each item to be completable in one agent loop. When the worker returns, its context is discarded; the orchestrator keeps only the verdict.

## The orchestrator's job

1. **Preflight once** (`work_preflight.py --spec-dir docs/specs`). Ensure the lifecycle labels exist (`status:doing`, `escalated`, `needs-human-review`). Stop on any gating failure.
2. **Select** (`select_work.py --autonomy afk`). This is the actionable queue: open, unflagged, unblocked (and not blocked by a stale-flagged blocker), autonomy-matched, not in flight elsewhere -- resumable-by-you first, then by `priority` (a live hook; make-issues does not stamp one today, so the default is by issue number), then issue number. **afk requires acceptance criteria:** an afk issue whose body has no `## Acceptance criteria` checklist is treated as hitl and excluded from the afk drain (the `afk` label alone cannot override a missing acceptance gate) -- an unattended worker must never build work it cannot verify as done. This applies to both provenance modes; a make-issues `amendment` with no authored criteria stays hitl.
3. **Dispatch a worker per issue.** Spawn a subagent with the worker brief below (the do-work session does this with its Task/subagent tool; the bundled `workflows/drain-queue.js` does it with `agent()`). Do **not** build in the orchestrator's own context -- not even for a single issue. That is the rule.
4. **Collect the verdict** (the contract below). Record it; do not absorb the worker's transcript.
5. **Review and fix each built PR** (every run, not behind a flag). For each `built` verdict run the review -> fix loop (below): a fresh reviewer (`do-pr-review`) posts findings and returns a count of open Critical/Major findings; if any, a fixer (`do-pr-fix`) addresses them and replies in-thread; re-review repeats until clean or `maxReviewRounds` is spent. A PR that can't be cleared is parked for a human (`review_unresolved`), never merged.
6. **Apply the terminal acceptance gate** (every review-clean PR -- see *Acceptance gate* below). Read the worker's **as-built ledger**: an issue is **acceptance-clean** only when every acceptance criterion is `met`. Any `deferred`/`mocked` entry (or a missing ledger) means the code does not yet satisfy the issue -- park it like an unconverged review (`review_unresolved`), never merging it as if done. Under `--dangerously` it may still merge, but each deferred/mocked entry gets a `needs-human-review` follow-up.
7. **Merge** (only under `--auto-merge`, and only for `built` verdicts that came back **review-clean AND acceptance-clean**): merge each green PR **serially** (autonomy + CI guards in the merge step, including a wait for the post-fix CI). A merge closes the issue COMPLETED and unblocks its dependents.
8. **Re-select and repeat** (under `--no-limit`): a fresh `select_work.py` pass surfaces issues a merge just unblocked. Keep an **attempted set** -- never re-dispatch an issue already tried this run -- so the loop terminates instead of rebuilding the same item. Stop when the limit is reached (**the default is one issue** -- a bare run does not loop; `--limit=<N>` caps at N; `--no-limit` runs until dry), when the queue is dry, or when only HITL / blocked / flagged items remain.
9. **Report** (every run): built, reviewed/fixed, the **acceptance summary** (fully met as-spec vs deferred/mocked), merged, parked-for-review, escalated, failed, still-blocked, and the remaining queue.

## The worker's job (one issue)

This is the brief a worker runs. Build **only** the one slice; do not widen scope or touch another issue.

1. **Claim it** -- `gh issue edit <N> --repo <owner/name> --add-assignee @me --add-label status:doing`. If it is already yours (a resumed run), continue from the branch rather than restarting.
2. **Read, in order** -- the issue (`gh issue view <N>`: Goal, What to build, the requirement + its EARS Acceptance criteria, the `## Verification` section (the proof plan: `method (covers) -- check` entries embedded from the requirement, when the spec carries them), Test plan, and the `make-issues:meta` block). The issue is self-contained; if you need the full rationale behind a `trace_adr` decision, read that ADR in `docs/specs/decisions/` -- but do not re-derive or edit the spec. **Provenance:** a `provenance: spec` issue embeds a requirement (the usual case); a `provenance: amendment` issue is self-contained the same way, but its requirement and acceptance criteria were AUTHORED into the body (there is no spec requirement behind it) and it anchors to a `feature` rather than a `trace_req`. Build against the acceptance criteria as written either way; you reached this worker only because the issue has them (a criteria-less issue is gated out at selection). If the issue cannot be built as written, escalate (below) instead of coding around it. **Under `--dangerously`** the worker does not escalate or wait for *implementation* problems: it resolves implementation ambiguity with best-practice defaults, mocks missing externals (`FIXME(dangerously)`), builds HITL too, and opens a `needs-human-review` follow-up for each decision -- **except an unsatisfiable acceptance criterion (a spec defect), which still escalates and stops the issue.** See `escalation-and-handback.md`, *Dangerous mode*. It still never edits the specs or scope.
3. **Build on a branch** -- `git switch -c <type>/issue-<N>-<short-slug>` off the default branch, following `do-git-workflow` (emoji-first Conventional Commits, one logical change per commit). Implement this slice only.
4. **Verify -- the build gate** -- detect and run what the repo has (check `package.json` scripts, `Makefile`, `pyproject.toml`, CI config, the repo `CLAUDE.md`): tests, then build, then lint, plus the issue's Test plan. **When the issue carries a `## Verification` section, execute its machine-runnable entries too**: a `test` entry means that test exists and passes (write it if it does not), an `analysis` entry means the reasoning is recorded, a `monitor` entry means the signal/alert is wired. A `demo`/`inspection` entry is a human-judgment proof -- do not fake it; it surfaces in the ledger as `deferred` (below). **No PR on a red gate.** Fix it if it is your slice's doing; otherwise escalate or return `failed`.
5. **Open the PR** -- `git push -u origin <branch>`, then fill `assets/pr-body-template.md` and `gh pr create`: `Closes #<N>` (the merge closes the issue COMPLETED and the link populates), the trace mirrored from the issue meta, the acceptance checklist, how it was verified, and the **`## As-built` ledger** (one row per acceptance criterion: `met` / `deferred` / `mocked`, with evidence). **Ready-for-review by default** (draft only to park an HITL decision).
6. **Status is GitHub state** -- the assignment, `status:doing`, the PR, and issue comments. **Never edit the make-issues managed regions** of the issue body (prose, `meta`, changelog). Track acceptance in the PR, not by ticking the issue's boxes.
7. **Fill the as-built ledger truthfully** -- for **each** acceptance criterion the issue carries, record one `as_built` entry: `{criterion, status: met|deferred|mocked, evidence}`. `met` needs real evidence (a passing test, a checked behavior); `mocked` is backed by a `FIXME(dangerously)` stub; `deferred` was not built. **When the issue carries a `## Verification` section, the evidence for a `met` row cites the verification entry it executed** (e.g. `test (negative): forced a gateway decline; asserts error banner + intact cart -- passing`), not a bare "works". A criterion whose only applicable proof is `demo`/`inspection` cannot be machine-`met`: record it `deferred` with the demo/inspection steps as the evidence -- that row is the human operator's checklist, and parking it is the gate working, not a failure. This is the terminal acceptance gate's input -- an honest `deferred`/`mocked` is correct; a `met` that was not really met is a defect.
8. **Return the verdict** and stop.

## The worker result contract

The worker returns this and nothing else -- it is the entire handoff back to the orchestrator:

```yaml
issue:    <number>
status:   built | escalated | failed
branch:   <branch name, when built>
pr_url:   <PR URL, when built>
gate:     <e.g. "tests+lint pass">
as_built:                       # one entry per acceptance criterion (the ledger)
  - criterion: <text or id>
    status:   met | deferred | mocked
    evidence: <how verified, or why deferred/mocked>
summary:  <one line>
```

- **built** -- PR open (and green CI), ready for the acceptance gate. `built` is *not* the same as done: the orchestrator still reads the `as_built` ledger and only treats the issue as complete when every criterion is `met` (the *Acceptance gate* below).
- **escalated** -- could not be built as written; the worker has commented the reason and added the `escalated` label (so the next select excludes it). The orchestrator routes it per `escalation-and-handback.md`; it never silently retries.
- **failed** -- the gate stayed red for a reason that is not an escalation. The orchestrator records it and the attempted-set keeps the loop from re-trying it this run.
- **`as_built`** -- the ledger the acceptance gate reads. The worker fills it from what it actually implemented; a missing or empty ledger reads as "acceptance not demonstrated" (not acceptance-clean).

## The review and merge gate

Every PR a worker opens is reviewed and fixed before the run is done with it -- on every run, not behind a flag. Each step is a fresh agent (the reviewer and fixer never share the builder's context).

1. **Review** -- a fresh agent runs `do-pr-review` against the PR's current diff: inline findings posted to GitHub, and a structured verdict back to the orchestrator. The control signal is **`blocking_open`** -- the count of unresolved Critical/Major findings in the current code.
2. **Fix** -- if `blocking_open > 0`, a fresh agent runs `do-pr-fix` on those findings: it edits, runs the build gate, pushes, and **always replies in-thread** (`Fixed.` / `Rejected.`) on each comment it addresses, then resolves those threads.
3. **Re-review** -- a fresh reviewer re-assesses the new diff. Repeat until `blocking_open == 0` or `maxReviewRounds` fix attempts (default 2) are spent.
4. **Outcome** -- clean -> on to the acceptance gate (below), then eligible to merge (under `--auto-merge`). Not clean after the cap -> comment the unresolved findings, add the `escalated` label (so the next `select_work` excludes it), leave the PR **open** for a human, and report it as `review_unresolved`. **Under `--dangerously`** the not-clean branch flips: instead of parking, open a `needs-human-review` follow-up issue for the residual findings (no `escalated` label) and let the PR proceed to merge -- which still gates on green CI (a red CI is flagged and left open, never merged).

The review is **context-independent**: the reviewer is a fresh worker that never shares the builder's context, regardless of which gh identity it uses.

**Review identity -- bot token vs same-identity fallback.** The reviewer's gh *identity* is configurable:

- **Bot review identity (set `GH_REVIEW_TOKEN`, or pass `args.reviewToken`).** The review step authenticates as the bot. Because the bot is not the PR author, GitHub accepts a real `REQUEST_CHANGES` review event, and GitHub's **native review state carries the signal**. This is the path that gives you a genuine independent second set of eyes at the GitHub level.
- **Same-identity fallback (no token).** Builder, reviewer, and fixer share one gh login, so GitHub forces the submitted review event to `COMMENT`, and `do-pr-fix` would normally skip the reviewer's "own" threads. The orchestrator handles both: the merge decision keys off the structured **`blocking_open`** count (not the GitHub review state), and the fixer is instructed to act on same-user threads and reply in-thread regardless. The review is still context-independent -- only the GitHub identity is shared.

## Acceptance gate (consistency != correctness)

The fingerprint gates upstream (make-spec, make-issues) prove the specs, issues, and build are mutually **consistent**. They do **not** prove the shipped code actually **satisfies** the acceptance criteria. The terminal acceptance gate closes that last gap -- and the **as-built ledger** is its record.

- **The ledger.** Every worker returns an `as_built` array: one entry per acceptance criterion the issue carries, each `{criterion, status: met|deferred|mocked, evidence}`, filled truthfully from what was actually implemented. A `met` entry has real evidence (a test, a checked behavior) -- and when the issue embeds a `## Verification` proof plan, the evidence **cites the verification entry executed**, which is what keeps "met" from meaning "looked fine". A `mocked` one is backed by a `FIXME(dangerously)` stub; a `deferred` one was not built (including a criterion whose only proof is `demo`/`inspection` -- a human-judgment row an unattended worker records but never claims). It is mirrored into the PR's `## As-built` section. make-issues marks judgment-proof-only requirements HITL at slicing time, so an AFK drain rarely hits them.
- **The gate (orchestrator).** An issue is **acceptance-clean** only when its ledger exists and **every** entry is `met`. If any is `deferred` or `mocked` (or the ledger is missing):
  - **Normal mode** -- the issue is NOT done. Reuse the review/park machinery: comment the deferred/mocked criteria on the PR, label the issue `needs-human-review`, leave the PR **open**, and report it as `review_unresolved` (the ledger is the reason). Never auto-merge it as if complete.
  - **`--dangerously`** -- consistent with that mode merging on green CI with open findings, it **may still merge**, but each deferred/mocked entry MUST get a `needs-human-review` follow-up, and they appear in the run summary. **The ledger is the debt record.**
- **What it is and is not.** This is a discipline plus a record, not a heavyweight verifier. It does **not** prove correctness; it **records and gates on** whether each criterion was actually met vs deferred/mocked. The run's **acceptance summary** reports issues fully met as-spec vs issues with deferred/mocked criteria.

## Serial by default, parallel by round

- **Serial (the baseline)** -- one worker at a time, in the main working tree. This already bounds context fully and is always safe.
- **Parallel (2-3, opt-in)** -- dispatch a round of workers **only when their issues are file-disjoint** (different areas of the tree). Each parallel worker runs in its **own git worktree** (`isolation: worktree`) so their uncommitted changes never collide; the worktree is removed automatically if a worker makes no change. Keep it to 2-3.
- **Caveats that keep parallel honest:** under `--auto-merge`, each merge moves the default branch, so later same-round PRs may need a rebase -- and two "independent" issues that touch the same file still conflict at PR/merge time. When unsure whether a batch is disjoint, run it serially. **Merges are always serial**, never concurrent.

## Resuming a killed run

A run killed mid-build leaves a branch and an assignment. Because `select_work.py` sorts resumable (already-yours) issues first, the next run picks the half-built issue back up. The resuming worker reconciles branch state first -- pull, re-run the gate -- rather than starting over.

## Draining the whole backlog

For an unattended drain, the orchestration above is encoded deterministically in `workflows/drain-queue.js` (run via the Workflow tool): preflight, then a loop of select -> parallel build workers -> review -> fix loop -> terminal acceptance gate -> serial auto-merge -> re-select, until the queue is dry (or the limit is hit). It takes `args.repo` and `args.skillDir`, plus `autoMerge`, `parallel` (1-3), `noLimit` (true = drain the whole queue) / `limit` (absent = **1**, the default bounded run; `0` = unlimited, same as `noLimit`; `N` = cap at N), `maxReviewRounds`, an optional `reviewToken` (the bot review identity; defaults to env `GH_REVIEW_TOKEN`), and optional `reviewSkillDir` / `fixSkillDir` (default: siblings of `skillDir`). There is no `dryRun` arg -- `--dry-run` is an interactive-only gate (below); the workflow builds without pausing. The script holds the loop and the verdicts; each build, review, and fix is still a fresh worker, and the run summary includes the **acceptance summary** (issues fully met vs with deferred/mocked criteria). See SKILL.md, *Execution model*.

## Dry run (`--dry-run`, interactive only)

`--dry-run` inserts a preview-and-approve gate before any build worker runs. The orchestrator does its read-only steps -- preflight and `select_work.py` -- to fix the in-scope set (honoring `--limit` / `--no-limit` / `--phase` / `--issue` / autonomy), dispatches a **planning worker** per in-scope issue, presents the consolidated plan, and **waits for the user to approve** before dispatching the real build workers. Nothing on GitHub or disk changes until then. This gate exists only in the interactive `/do-work` session; a headless run or the drain workflow builds straight through, because no one is there to approve.

### The planning worker's job (one issue, read-only)

A planning worker gets the same pointer a build worker gets -- the issue number and repo -- and the same reading list, but it **writes nothing**. It produces a plan, not a PR.

1. **Read, in order** -- the issue (`gh issue view <N>`: Goal, What to build, the requirement + its EARS Acceptance criteria, Test plan, and the `make-issues:meta` block), the governing ADR in `docs/specs/decisions/` by its `trace_adr` when the rationale matters, and the **relevant existing code** so the outline is grounded in what is really there.
2. **Do not mutate anything** -- no `gh issue edit` (no assignment, no `status:doing`, no labels), no `git switch`/branch, no edits or commits, no `git push`, no PR. It is the strict read-only counterpart of the build worker; the whole point of `--dry-run` is that approval comes *before* the first side effect.
3. **Return a build outline** and stop -- this is the planning worker's entire handoff:

```yaml
issue:      <number>
title:      <issue title>
branch:     <type>/issue-<N>-<slug>     # the branch it WOULD create
approach:   <a few lines: how it would build this slice>
files:                                  # files it expects to create or change
  - <path> -- <why>
verify:     <the build gate it would run + the issue's Test plan>
acceptance:                             # the criteria it must meet, from the issue
  - <criterion>
risks:                                  # ambiguities, gaps, or likely escalations
  - <e.g. "governing ADR is silent on X" / "criterion C may be unsatisfiable -> would escalate">
```

### The orchestrator's dry-run job

1. Preflight + select (read-only), as above, to get the ordered in-scope queue.
2. Dispatch a planning worker per in-scope issue (serial, or parallel like a build round) and collect the outlines. A worker that finds a likely escalation reports it in `risks` -- it still does not touch the issue.
3. **Present the plan and stop.** Show the run posture -- the in-scope issues in order; the review -> fix -> acceptance-gate pipeline; the merge posture under `--auto-merge` / `--dangerously`, including the **HITL auto-merge manifest** when `--dangerously` is set -- then each issue's outline. Ask the user to approve.
4. **On approval**, dispatch ordinary build workers for the same issues (the normal orchestrator loop). If the user declines or narrows scope, stop; a `risks` entry that flags a spec/design defect is a cue to hand back upstream (`/make-spec` / `/make-arch` / `/make-issues`) before re-running.

The outline covers only the **currently-actionable** in-scope issues; it cannot foresee issues that only unblock after a merge later in the run (the forward-only cascade), so with `--no-limit` the plan is the first tier, not the full eventual cascade.
