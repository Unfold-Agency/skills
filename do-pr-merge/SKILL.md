---
name: do-pr-merge
description: This skill should be used when the user asks to "merge a PR", "merge this pull request", "merge PR #N", "merge <github PR url>", "land this PR", or "squash and merge". Merges an open GitHub PR by dispatching a Haiku sub-agent that runs the merge and -- by default -- deletes the head branch. The merge method defaults to the repository's configured strategy (a linear method when available); pass --squash to squash-merge, --merge / --rebase to force a method, and --no-delete to keep the branch. Action skill -- it changes the base branch by merging. It does not review the PR (use do-pr-review) or address review feedback (use do-pr-fix).
argument-hint: <pr-number-or-url> [--squash | --merge | --rebase] [--no-delete]
allowed-tools: Bash(gh:*), Bash(git:*), Task
---

# Merge a PR

Merge a single open GitHub PR (by number or URL) and, by default, delete its head branch. This skill **only merges** -- it does not review the diff (`do-pr-review`), implement feedback (`do-pr-fix`), or watch CI. The actual merge runs in a **Haiku sub-agent**; the few `gh` calls a merge takes are exactly the cheapest tier's job (the same split `do-work` uses for its merge step).

## How it runs

The session you're in is the **orchestrator**: it checks preconditions, parses the invocation, and dispatches **one Haiku sub-agent** to do the merge. The worker resolves the PR, picks the merge method, runs `gh pr merge`, verifies the result, and returns a compact verdict. The orchestrator never merges in its own context -- it hands the worker a precise brief and reports the verdict back.

## Merge method (default = repo's configured strategy)

`gh pr merge` requires an explicit method when run non-interactively, so the worker resolves one:

- **No method flag (default)** -- query the repo's allowed methods and pick a **linear** strategy: `--rebase` if allowed (linear history, commits preserved), else `--squash` (linear, collapsed), else `--merge` (merge commit). This is why `--squash` is a *separate* opt-in: the default leans linear without collapsing history.
- **`--squash`** -- squash-merge (one commit).
- **`--merge`** -- merge commit.
- **`--rebase`** -- rebase-merge.

If an explicit method is passed but the repo disallows it, `gh` errors -- surface that error rather than silently switching methods. The worker always reports which method it used.

## Branch deletion (default = delete)

By default the head branch is deleted after a successful merge (`--delete-branch`). Pass **`--no-delete`** to keep it.

## Step 0 -- Preconditions (orchestrator)

```bash
gh auth status   # stop and tell the user to run `gh auth login` if this fails
```

## Step 1 -- Parse the invocation (orchestrator)

- **Target** -- a PR number (e.g. `42`) or a full PR URL. Required. For a **number** target, first confirm you're inside the intended repo (`git rev-parse --is-inside-work-tree`) -- `gh` infers `owner/repo` from the local checkout. A **URL** target carries its own `owner/repo`, so it works from any directory; skip the git check.
- **Method override** -- at most one of `--squash` / `--merge` / `--rebase`. None = repo default (linear-preferred, above).
- **Delete** -- delete the head branch unless `--no-delete` is present.

Resolve identifiers once so the worker uses them explicitly:

```bash
gh pr view <target> --json url,number,state,isDraft,headRefName,baseRefName,mergeable,mergeStateStatus
```

Parse `OWNER`, `REPO`, `NUMBER` from the `url` field (`https://github.com/OWNER/REPO/pull/N`). Use `$OWNER/$REPO` explicitly in the brief so a URL target in another repo merges correctly.

## Step 2 -- Dispatch the Haiku merge worker

Spawn **one sub-agent on the Haiku model** (via the Task tool) with the brief below. Substitute the parsed target, `$OWNER/$REPO`, the chosen method (or "repo default"), and the delete decision.

> **Merge PR `<target>` in `$OWNER/$REPO`, but only if it is safe to merge. Report the outcome.**
>
> 1. **Inspect:** `gh pr view <target> --repo $OWNER/$REPO --json number,state,isDraft,mergeable,mergeStateStatus,headRefName,baseRefName,url`.
>    - If `state == MERGED` -> it's already merged. Return `merged=true, detail="already merged"`, no action.
>    - If `state != OPEN` (e.g. `CLOSED`) -> do **not** merge. Return `merged=false, detail="PR is <state>, not open"`.
>    - If `isDraft == true` -> do **not** merge. Return `merged=false, detail="PR is a draft -- mark it ready first"`.
>    - If `mergeable == CONFLICTING` -> do **not** merge. Return `merged=false, detail="merge conflicts -- rebase/resolve first"`.
> 2. **Resolve the method.** If an explicit method was given (`--squash`/`--merge`/`--rebase`), use it. Otherwise query the repo's allowed methods and pick a linear one: `gh api repos/$OWNER/$REPO --jq '{merge: .allow_merge_commit, squash: .allow_squash_merge, rebase: .allow_rebase_merge}'` -> `--rebase` if allowed, else `--squash`, else `--merge`.
> 3. **Merge:** `gh pr merge <target> --repo $OWNER/$REPO <method-flag> [--delete-branch]`. Include `--delete-branch` unless `--no-delete` was set. Do **not** use `--admin` -- let branch protection (required checks/reviews) block the merge if it must; if `gh` errors, return `merged=false` with the verbatim error in `detail`.
> 4. **Verify:** `gh pr view <target> --repo $OWNER/$REPO --json state,mergedAt`. Confirm `state == MERGED`.
> 5. **Return** a compact verdict: `merged` (bool), `method` (rebase|squash|merge), `branch_deleted` (bool), `detail`, `url`.

## Step 3 -- Recap (orchestrator)

Report the worker's verdict succinctly: merged or not, the method used, whether the branch was deleted, and the PR URL. If the merge was refused or failed, state the reason from `detail`. No fluff.

## Guardrails

- **Only merges** -- never reviews, edits, or pushes code. Review is `do-pr-review`; fixes are `do-pr-fix`.
- **Merges on invocation** -- the explicit target + flags are the authorization; no extra confirmation step. But the worker refuses an unsafe merge (closed, draft, or conflicting PR) and reports why.
- **Respects branch protection** -- no `--admin` bypass. If required checks or reviews block the merge, `gh` errors and that error is surfaced; the skill does not force it.
- **Does not wait for CI** -- it merges the PR as-is (GitHub still enforces any *required* checks). To gate on a full green run first, watch CI separately (e.g. `gh pr checks <target> --watch`) before invoking.
- **Default method is the repo's** -- linear-preferred (`rebase -> squash -> merge`); `--squash`/`--merge`/`--rebase` override. An override the repo disallows surfaces `gh`'s error rather than silently switching.
- **Deletes the branch by default**; `--no-delete` keeps it. Never force-deletes a branch that failed to merge.
- **One PR per invocation** -- pass a single number or URL.
