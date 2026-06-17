---
name: do-git-workflow
description: This skill should be used whenever working in a Git repository and the user asks to "commit", "make a commit", "create a branch", "start work on", "open a PR", "create a pull request", or whenever code changes are about to be committed. Enforces a branch-first workflow, Conventional Commits with GitMoji prefixes, type/short-description branch names, and pull request creation via the gh CLI.
allowed-tools: Bash(git:*), Bash(gh:*)
---

# Git workflow

Enforce a consistent Git workflow in every repository:

1. **Branch first** — never commit directly to the default branch. Work happens on a `type/short-description` branch.
2. **Conventional Commits + GitMoji** — commit subjects follow `<emoji> <type>(scope): description`, emoji first.
3. **Pull requests** — open a PR via the `gh` CLI when the work is ready. **Ready for review** when the coding work is complete; **draft** only for a mid-work PR you know still has more to do.

## Step 0 — Verify this is a Git repository

Before doing anything else, confirm the working directory is inside a Git repo:

```bash
git rev-parse --is-inside-work-tree
```

If this fails (not a repo), this skill does not apply — skip it silently and proceed normally. Do not create branches, commits, or PRs in a non-repo directory.

## Step 1 — Branch first

Before the first commit of a unit of work, ensure work is happening on a feature branch, not the default branch.

```bash
# Current branch
git rev-parse --abbrev-ref HEAD

# Default branch (falls back to main/master if origin/HEAD is unset)
git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@' | grep . \
  || (git branch -r | grep -qE 'origin/(main)$' && echo main || echo master)
```

- If currently on the default branch (`main`/`master`) or any protected branch, create a new branch before committing:

  ```bash
  git switch -c <type>/<short-description>
  ```

- If already on a suitable feature branch, stay on it.

**Branch naming:** `<type>/<short-description>`
- `type` matches the Conventional Commit type of the intended work (see table below).
- `short-description` is kebab-case, concise, no ticket prefix.
- Examples: `feat/user-login`, `fix/null-crash`, `refactor/auth-service`, `docs/api-readme`.

## Step 2 — Commit format

Commit subjects use Conventional Commits with a leading GitMoji:

```
<emoji> <type>(<optional-scope>): <description>
```

Rules:
- **Emoji first**, then the conventional `type(scope):` prefix.
- Description in **imperative mood**, **lowercase**, **no trailing period**.
- Keep the subject line **≤72 characters**.
- An optional body (separated by a blank line) explains **why**, wrapped at ~72 columns.
- Keep the `Co-Authored-By` trailer that Claude Code appends.
- One logical change per commit — do not bundle unrelated changes.

### Type → emoji map

| type | emoji | use |
|---|---|---|
| feat | ✨ | new feature |
| fix | 🐛 | bug fix |
| docs | 📝 | documentation |
| style | 🎨 | formatting / code structure |
| refactor | ♻️ | code change, no behavior change |
| perf | ⚡️ | performance |
| test | ✅ | tests |
| build | 👷 | build system / dependencies |
| ci | 💚 | CI configuration |
| chore | 🔧 | tooling / config |
| revert | ⏪️ | revert a change |
| init | 🎉 | initial commit |
| security | 🔒️ | security fix |
| remove | 🔥 | remove code or files |
| wip | 🚧 | work in progress |

### Examples

```
✨ feat(auth): add email/password login flow
🐛 fix(api): handle null response from /users endpoint
♻️ refactor(parser): extract token reader into its own module
📝 docs(readme): document local setup steps
```

A commit with a body:

```
🐛 fix(cache): evict stale entries on config reload

The cache kept serving values from the previous config because the
reload path never cleared it. Clear the store before re-warming.
```

## Step 3 — Open a pull request

When the work is ready for a PR, push the branch and open one. Default to **ready for review**; open a **draft** only when you are deliberately putting up a mid-work PR with known remaining work.

```bash
# Push and set upstream
git push -u origin <branch>

# Completed work — open ready for review (the default)
gh pr create \
  --title "<emoji> <type>(<optional-scope>): <summary>" \
  --body "<body>"

# Mid-work — open as a draft because there is more to do
gh pr create --draft \
  --title "<emoji> <type>(<optional-scope>): <summary>" \
  --body "<body>"
```

- The PR **title** mirrors the commit convention (emoji-first Conventional Commit).
- The PR **body** summarizes *what* changed and *why*, and includes a brief test plan.
- If `gh` is not authenticated (`gh auth status` fails), tell the user instead of guessing.

## Notes & guardrails

- **One logical change per commit**; stage selectively rather than `git add -A` when unrelated changes are present.
- **Never force-push a shared branch.** Only force-push (`--force-with-lease`) on a personal feature branch when explicitly needed.
- **Respect existing repo conventions.** If a repo clearly uses a different commit or branch convention (check `git log` / CONTRIBUTING), surface the conflict to the user rather than silently overriding it.
- **Commit and push only when asked** — follow normal session rules about when to commit.
