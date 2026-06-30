---
name: do-git-prune
description: This skill should be used when the user asks to "prune branches", "delete merged branches", "clean up local branches", "remove stale branches", "tidy up git branches", or after merging PRs when local branches pile up. Deletes local git branches that are fully merged into the default branch -- both ancestor-merged (fast-forward / merge-commit) and content-merged via a squashed or rebased PR -- by dispatching a Haiku sub-agent that does the analysis and deletion. Never deletes the default branch, the current branch, or any branch with an open PR. Action skill -- it deletes branches. Pass --dry-run to preview, --remote to also delete merged remote branches, --yes to skip the confirmation, and --base=<branch> to prune against a base other than the repo default.
argument-hint: "[--dry-run] [--remote] [--yes] [--base=<branch>]"
allowed-tools: Bash(git:*), Bash(gh:*), Task
---

# Prune merged branches

Delete the local branches that are fully merged and just clutter `git branch` now. The session you're
in is the **orchestrator**: it checks preconditions, resolves the default branch and the protected
set, then dispatches **one Haiku sub-agent** to do the analysis and the deletions. The few `git` /
`gh` calls a prune takes are exactly the cheapest tier's job -- the same orchestrator-plus-Haiku split
`do-pr-merge` and `do-work` use for their merge step. The orchestrator never deletes in its own
context; it hands the worker a precise brief and reports the verdict back.

## What counts as "merged"

A branch is safe to delete only with **positive evidence** it is already in the base. Two cases:

- **Ancestor-merged** -- the branch tip is reachable from the base (`git branch --merged <base>`
  lists it). This covers fast-forward and merge-commit merges. Delete with `git branch -d` (which
  itself refuses anything not merged -- a safety net).
- **Content-merged** -- the branch was **squashed or rebased** into the base, so its tip is *not* an
  ancestor and `git branch -d` would refuse it, but its PR is merged. Confirm a **merged PR whose
  `headRefName` exactly matches the branch**, then delete with `git branch -D`. The merged PR is the
  authorization for the force delete; without it, do not force-delete.

Anything with **no merge evidence** (not an ancestor, no merged PR) is left alone and reported.

## What is never deleted

- The **default branch** (`main`/`master`) and the **current branch** (`git branch --show-current`).
- Any branch that is the head of an **open PR** (`gh pr list --state open`).
- Any branch lacking positive merge evidence (above).

## Flags

- **`--dry-run`** -- analyze and report what *would* be deleted (by method), delete nothing.
- **`--remote`** -- after local deletion, also delete the **merged** branch on `origin`
  (`git push origin --delete`), but only for branches with a confirmed merged PR. Off by default;
  most repos auto-delete the head branch on merge, so the remote is usually already clean.
- **`--yes`** -- skip the confirmation prompt (for unattended / headless runs).
- **`--base=<branch>`** -- prune against this base instead of the repo default.

## Step 0 -- Preconditions (orchestrator)

```bash
gh auth status                          # stop and tell the user to run `gh auth login` if this fails
git rev-parse --is-inside-work-tree     # must be inside a git repo
git symbolic-ref -q HEAD                 # must be ON a branch (not detached) -- stop if detached
git fetch --prune origin                 # update remote-tracking refs and drop stale ones
```

## Step 1 -- Resolve base + protected set (orchestrator)

```bash
BASE="${base:-$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name)}"   # e.g. main
CURRENT=$(git branch --show-current)
gh pr list --state open --limit 300 --json headRefName --jq '.[].headRefName'          # open-PR heads
```

The protected set is `BASE` + `CURRENT` + every open-PR head. Pass all of it to the worker explicitly
so it cannot delete a branch a human still needs.

## Step 2 -- Dispatch the Haiku prune worker

Spawn **one sub-agent on the Haiku model** (via the Task tool) with the brief below. Substitute
`BASE`, the protected set, and the parsed flags (`dry-run`, `remote`, `yes`).

> **Prune the local branches that are fully merged into `<BASE>` in this repo. Report what you
> deleted and what you skipped.**
>
> **Never touch these (protected):** `<BASE>`, the current branch `<CURRENT>`, and the open-PR heads
> `<open-pr-heads>`. If any of these appears in your candidate list, drop it.
>
> 1. **Candidates:** `git branch --format='%(refname:short)'` minus the protected set.
> 2. **Classify each candidate:**
>    - In `git branch --merged <BASE>`? -> **ancestor-merged**, delete with `git branch -d <b>`.
>    - Otherwise check `gh pr list --state merged --limit 300 --json number,headRefName --jq '.[] | select(.headRefName=="<b>") | .number'`. A match -> **content-merged** (squash/rebase), delete with `git branch -D <b>`; record the PR number.
>    - No match -> **skip**, reason `"no merge evidence"`.
> 3. **If `--dry-run`:** do not delete anything; just return the classification.
> 4. **Delete** each merged branch with the method above. `git branch -d` failing is a signal the
>    branch is NOT actually merged -- do **not** escalate it to `-D` unless a merged PR confirmed it.
> 5. **If `--remote`:** for each branch you deleted that had a confirmed merged PR and still exists on
>    origin (`git ls-remote --exit-code --heads origin <b>`), run `git push origin --delete <b>`.
> 6. **Return** a compact verdict: `deleted` (list of `{branch, method, pr}`), `skipped` (list of
>    `{branch, reason}`), `remote_deleted` (list, if `--remote`), and counts.

If `--yes` was **not** passed and this is not a dry run, the orchestrator first shows the worker's
proposed deletion list (run the worker in dry-run to get it) and asks for confirmation, then
dispatches the real deletion. With `--yes`, dispatch the deletion directly.

## Step 3 -- Recap (orchestrator)

Report the worker's verdict: how many branches deleted (split ancestor `-d` vs PR-confirmed `-D`),
which were skipped and why, and any remote deletions. List the skipped branches by name -- they are
the ones the user may want to look at. No fluff.

## Guardrails

- **Positive evidence only.** Delete a branch only if it is an ancestor of the base *or* has a merged
  PR with a matching head. Never force-delete (`-D`) on a guess -- the merged PR is the only license.
- **Protected set is absolute** -- never the default branch, the current branch, or an open-PR head,
  even if they somehow look merged.
- **`--dry-run` deletes nothing.** Default (no `--yes`) confirms before deleting.
- **Local by default** -- only touches `origin` with `--remote`, and only for PR-confirmed branches.
- **Never force-push**, and never delete a remote branch that has an open PR.
- **Prunes only** -- it does not merge (`do-pr-merge`), review (`do-pr-review`), or open PRs
  (`do-git-workflow`).
