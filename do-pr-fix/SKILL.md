---
name: do-pr-fix
description: This skill should be used after a PR has been reviewed, when the user asks to "address the PR comments", "fix the requested changes", "implement the review feedback", "resolve the PR comments", "make the changes requested on PR #N", or "fix everything on the PR". Implements the valid requested changes on a GitHub PR branch, replies in-thread explaining each fix, runs tests/build if present, and pushes the commits to the PR. Edits code and pushes — the back-half of the review loop.
argument-hint: <pr-number-or-url> [--resolve]
allowed-tools: Bash(gh:*), Bash(git:*), Read, Grep, Glob, Edit, Write
---

# Fix a reviewed PR

Given an already-reviewed GitHub PR, implement the valid requested changes, reply in-thread explaining each fix, and push the commits to the PR branch. This is the back-half of the review loop — the companion to `do-pr-review` (which is comment-only). It **edits code and pushes**.

## Comment style (hard requirement)

- Succinct and direct. No praise, no emoji, no filler, no color commentary.
- Fix replies state exactly **what was fixed and how**: `Fixed. <what changed and how>.`
- Rejections state only the reason: `Rejected. <reason>.`

## Step 0 — Preconditions

```bash
gh auth status                       # stop if not authenticated
git rev-parse --is-inside-work-tree  # must be inside a git repo
```
Parse the optional `--resolve` flag from the invocation.

## Step 1 — Resolve the PR + push permission

```bash
gh pr view <target> --json url,number,state,headRefName,headRefOid,baseRefName,author,isCrossRepository,maintainerCanModify
```

- Parse `OWNER`, `REPO`, `NUMBER` from the `url` field (`https://github.com/OWNER/REPO/pull/N`). Use these **explicitly** in every `gh api repos/$OWNER/$REPO/...` call.
- `ME=$(gh api user --jq .login)`.
- **Push permission:** allowed if `isCrossRepository == false` **OR** `maintainerCanModify == true`. If neither holds (fork PR with modify disabled), stop and tell the user the branch can't be pushed to.
- If `state` is not `OPEN`, warn before continuing.

## Step 2 — Check out the PR branch

```bash
gh pr checkout <target>   # sets upstream; a later `git push` updates the PR (fork or origin)
```
Record the current HEAD (`git rev-parse HEAD`) as the starting point so the work is traceable.

## Step 3 — Enumerate review threads to address

Fetch threads with their node `id` (needed to resolve later) and resolved state:

```bash
gh api graphql -f query='
query($owner:String!,$repo:String!,$number:Int!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$number){
      reviewThreads(first:100){ nodes{
        id
        isResolved
        isOutdated
        comments(first:50){ nodes{ databaseId author{login} path line body } } }
      }
    }
  }
}' -F owner=$OWNER -F repo=$REPO -F number=$NUMBER
```

Build a work list of every thread where `isResolved == false` (any author, including bots). Skip resolved/outdated threads and threads authored solely by `$ME`. For each, capture the thread's `id` (reply/resolve anchor: node `id` for resolve, **first comment's `databaseId`** for the reply).

## Step 4 — Triage each thread

For each thread, read the referenced code (`Read`/`Grep`) and judge validity against the actual code and repo conventions (`CLAUDE.md` / CONTRIBUTING).

- **Valid** → implement the change with `Edit`/`Write`. Note the exact change for the reply.
- **Invalid** → make no edit; queue a `Rejected. <reason>.` reply.

## Step 5 — Commit the fixes (grouped by area)

Follow the `do-git-workflow` conventions. Stage selectively and create a **few logical commits grouped by file/concern** — not one commit per thread, not one giant blob.

- Subject: `<emoji> <type>(scope): description` (emoji-first Conventional Commit), imperative, lowercase, ≤72 chars.
- Keep the `Co-Authored-By` trailer.
- Type→emoji: `feat ✨`, `fix 🐛`, `docs 📝`, `style 🎨`, `refactor ♻️`, `perf ⚡️`, `test ✅`, `build 👷`, `ci 💚`, `chore 🔧`, `security 🔒️`, `remove 🔥`.

Track which commit addressed which thread so replies can reference the SHA.

## Step 6 — Verify before pushing

Detect the project's test/build/lint commands (check `package.json` scripts, `Makefile`, `pyproject.toml`, CI config, repo `CLAUDE.md`) and run what exists — tests first, then build/lint.

If anything fails, **do not push.** Report the failure and stop so the user can decide. Only proceed when verification passes (or there is nothing to run).

## Step 7 — Push to the PR branch

```bash
git push                          # upstream set by gh pr checkout
# fallback if upstream unset:
git push -u origin <headRefName>
```
Never force-push a shared branch.

## Step 8 — Reply in-thread for every triaged thread

After the push (so the fix is live), reply under each thread's first comment:

```bash
gh api repos/$OWNER/$REPO/pulls/$NUMBER/comments/<FIRST_COMMENT_DATABASE_ID>/replies \
  -f body='Fixed. <what changed and how>.'    # or: Rejected. <reason>.
```

Reference the relevant commit SHA in fix replies where useful. Succinct — no color commentary.

## Step 9 — Optionally resolve threads (`--resolve`)

Only when `--resolve` was passed, resolve **every thread addressed this run — both Fixed and Rejected.** Replying with a reason (fixed or rejected) is the final word on the thread, so close it. Leave only untouched/skipped threads open.

Iterate over the **full addressed work-list** from Step 4 (not a subset) and run this mutation once per thread:

```bash
gh api graphql -f query='
mutation($threadId:ID!){
  resolveReviewThread(input:{threadId:$threadId}){ thread{ id isResolved } }
}' -F threadId='<THREAD_NODE_ID>'
```

Without the flag, resolve nothing — leave threads for the reviewer. Use the thread node `id` here, NOT the comment `databaseId`.

## Step 10 — Recap

Print: commits pushed (count + subjects), threads fixed vs rejected, whether verification ran and passed, whether threads were resolved, and the PR URL. No fluff.

## Guardrails

- **Push only when verification passes** — report failures instead of pushing broken code.
- **Respect push permission** (fork + `maintainerCanModify`) before checking out / pushing.
- **Straightforward replies** — what was fixed and how, or why rejected. No praise/emoji/color commentary.
- **Group commits by area** — don't bundle unrelated changes into one commit.
- **Never force-push.** Never resolve a thread unless `--resolve` is set; with it, resolve every thread addressed this run (Fixed or Rejected), never untouched/skipped ones.
- **No duplicate replies on re-run** — skip threads already answered by `$ME`.
- This skill consumes existing review threads; it does not re-review the PR (`do-pr-review`) or open a new PR (`do-git-workflow`).
