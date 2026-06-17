---
name: do-pr-review
description: This skill should be used when the user asks to "review a PR", "review pull request #N", "review <github PR url>", "code review this PR", "validate the comments on a PR", "respond to review comments", or "address PR feedback". Reviews a GitHub PR diff and posts inline review comments, validates or rejects existing review comments by replying in-thread, and submits a review verdict via the gh CLI. Comment-only — never edits code.
allowed-tools: Bash(gh:*), Bash(git:*), Read, Grep, Glob
---

# Review a PR

Review a GitHub pull request (by number or URL) and post results back to the PR:

1. Review the diff and post **inline review comments**.
2. Read **existing review comments** (any author, including bots) and **validate or reject** each by **replying in-thread**.
3. Submit a **review verdict** (APPROVE / REQUEST_CHANGES / COMMENT) based on severity.

This skill is **comment-only** — it never edits files or commits. It posts directly, with no preview/confirmation step.

## Comment style (hard requirement)

- Succinct and direct. No praise, no emoji, no filler ("good catch!", "great work", "nice"), no colorful language.
- Each comment states only **what** is suggested or **why** something is rejected, with a short description.
- Lead findings with their severity: `Critical:`, `Major:`, `Minor:`, `Nit:`.
- Validation replies use exactly: `Validated. <reason>.` or `Rejected. <reason>.`

## Step 0 — Preconditions

```bash
gh auth status
```
If this fails, stop and tell the user to run `gh auth login`. Do not guess credentials.

## Step 1 — Resolve the PR target

Accept either a number (e.g. `42`) or a full URL. Resolve identifiers once:

```bash
gh pr view <target> --json url,number,state,title,headRefOid,headRefName,baseRefName,isDraft,author,files
```

- Parse `OWNER`, `REPO`, `NUMBER` from the `url` field (`https://github.com/OWNER/REPO/pull/N`). Use these **explicitly** in every `gh api repos/$OWNER/$REPO/...` call so URL targets in other repos work — do not rely on `:owner/:repo`.
- `COMMIT_ID=<headRefOid>` — required for inline comments.
- `ME=$(gh api user --jq .login)` — the authenticated user.
- Note `author.login` (the PR author).
- If `state` is not `OPEN`, warn the user before continuing.

## Step 2 — Gather context

```bash
gh pr diff <target>             # unified diff to review
gh pr diff <target> --name-only # changed files
```

Use `Read`/`Grep`/`Glob` to inspect surrounding code and any repo `CLAUDE.md` / contributing conventions before judging. Review against the project's actual standards, not assumptions.

## Step 3 — Review the diff

Evaluate each change across five axes:

- **Correctness** — bugs, edge cases, error paths, off-by-one, race conditions.
- **Security** — input validation, secrets, authz, injection, unsafe handling of external data.
- **Performance** — N+1 queries, unbounded loops, needless allocation/re-render.
- **Readability / Maintainability** — naming, control flow, dead code, simplification.
- **Architecture / Reuse** — duplication, module boundaries, reusing existing utilities instead of new code.

For each finding:
- Tag severity: **Critical / Major / Minor / Nit**.
- Map it to `path` + `line`, with `side` = `RIGHT` for added/current code, `LEFT` for removed code.
- Only comment on lines present in the diff — GitHub rejects comments on unchanged lines.
- Where a concrete fix exists, include a GitHub ```suggestion block in the body.

## Step 4 — Validate existing review comments (reply in-thread)

Fetch review threads with resolved state via GraphQL (the REST `/pulls/{n}/comments` endpoint does **not** expose `isResolved`):

```bash
gh api graphql -f query='
query($owner:String!,$repo:String!,$number:Int!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$number){
      reviewThreads(first:100){ nodes{
        isResolved
        isOutdated
        comments(first:50){ nodes{ databaseId author{login} path line body } } }
      }
    }
  }
}' -F owner=$OWNER -F repo=$REPO -F number=$NUMBER
```

For each thread where `isResolved == false` and the thread is **not** authored solely by `$ME`:
- Assess the suggestion against the actual code.
- Reply under the thread's **first comment's `databaseId`**:

```bash
gh api repos/$OWNER/$REPO/pulls/$NUMBER/comments/<FIRST_COMMENT_DATABASE_ID>/replies \
  -f body='Validated. <reason>.'    # or: Rejected. <reason>.
```

Skip threads that are resolved, outdated, or already answered by `$ME`.

## Step 5 — Submit the review (inline findings + verdict)

Post all inline findings and the verdict in a single review call. Use line-based comments (modern API; `position` is the legacy fallback):

```bash
gh api repos/$OWNER/$REPO/pulls/$NUMBER/reviews -X POST \
  -f commit_id="$COMMIT_ID" \
  -f event="<EVENT>" \
  -f body="<succinct summary>" \
  -f 'comments[][path]=src/foo.ts' -F 'comments[][line]=42' -f 'comments[][side]=RIGHT' \
  -f 'comments[][body]=Major: <finding>. <why>.

```suggestion
<fixed code>
```'
  # repeat the three comments[] lines per finding
```

**Verdict logic:**
- Any **Critical** or **Major** finding → `REQUEST_CHANGES`.
- Only **Minor** / **Nit** findings → `COMMENT`.
- No actionable findings and no open threads → `APPROVE`.

**Self-PR guardrail:** GitHub forbids approving or requesting changes on your own PR. If `author.login == $ME`, silently force `event=COMMENT`. Do **not** mention self-approval in the summary — just give the normal succinct summary.

If `gh api` rejects a single comment as outside the diff, drop that comment and continue — do not fail the whole review.

## Step 6 — Recap

Print a short recap to the user: verdict, number of inline comments posted, number of threads validated/rejected, and the PR URL. No fluff.

## Guardrails

- **Comment-only** — never edit files, apply suggestions, or commit.
- **Post directly** — no confirmation step — but avoid duplicates: on a re-run, check existing comments first and skip findings/replies already posted by `$ME`.
- **Style** — succinct, no praise/emoji/colorful language; use the `Critical:/Major:/Minor:/Nit:` prefixes and the `Validated./Rejected.` reply templates.
- **Respect repo conventions** — judge against the project's stated standards; surface conflicts rather than imposing personal preference.
