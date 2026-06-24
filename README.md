# Skills

A collection of **Claude Agent Skills** maintained by Unfold Agency. Each skill packages a repeatable workflow -- instructions, templates, reference material, and helper scripts -- that Claude loads on demand and uses across conversations.

Skills follow the [Agent Skills](https://agentskills.io) open standard, so the same skill folder works in **Claude Code** (the CLI and IDE/desktop coding agent) and in the **Claude apps** (the desktop app and claude.ai).

## What's in this repo

Each top-level directory is one skill. A skill is a folder with a `SKILL.md` at its root, plus any supporting files it needs:

```
<skill-name>/
├── SKILL.md          # required: frontmatter + instructions
├── assets/           # optional: templates, schemas
├── references/       # optional: detailed guidance loaded on demand
├── scripts/          # optional: helper scripts Claude runs via bash
└── workflows/        # optional: deterministic multi-agent orchestration scripts
```

### Naming convention

Name a skill after what it does, with a prefix that signals its kind:

- **`make-<thing>`** -- the skill **produces an output**: a document or artifact you read, review, and sign, not code. `<thing>` is the deliverable. Examples: `make-prd`, `make-tdd`, `make-issues`.
- **`do-<thing>`** -- the skill **performs an action**: writing code, manipulating files, driving a process that changes the repo or the world. `<thing>` is the work. Example: `do-work`.

The test is output vs. action: if the skill hands back an artifact, it is `make-`; if it changes the codebase, it is `do-`. The folder name, the `name` field in `SKILL.md`, and the slash command all share the name, so `make-prd/` is invoked as `/make-prd` and `do-work/` as `/do-work`.

- Lowercase letters, numbers, and hyphens only (the same characters the `name` field allows).
- Keep `<thing>` short and concrete -- the artifact for `make-` (`make-prd`, `make-tdd`), the work for `do-` (`do-work`) -- not a vague activity (`prd-author`) or a bare verb (`generate`).
- The `# Heading` inside a `SKILL.md` is a readable form of the same imperative -- `# Make a PRD`, `# Do work`. Only the machine `name`/folder must match the prefix form exactly.

If you know the output or the action, you know the command.

### The pipeline skills

These four chain end to end -- see [How these skills chain](#how-these-skills-chain).

| Skill | What it does |
|---|---|
| [`make-prd`](./make-prd) | Generates and amends Product Requirements Documents from discovery material, with citation discipline, a derived machine-readable data file, and a validator. |
| [`make-tdd`](./make-tdd) | Generates and amends Technical Design Documents from an approved PRD -- recommend-then-refine architecture, full PRD-to-design traceability, a derived data file, and a validator. |
| [`make-issues`](./make-issues) | Turns an approved, version-locked PRD and TDD into traceable GitHub Issues and keeps them in sync as the TDD changes -- thin work items, AFK/HITL autonomy flags, a version-lock gate, and a stale-resistant reconciliation engine. |
| [`do-work`](./do-work) | Builds the project from those GitHub Issues -- drains the actionable backlog by default (cap with `--limit=<N>`), implements each issue on a branch, runs the build gate, opens a PR that closes it, and then **reviews and fixes that PR** (via `do-pr-review` / `do-pr-fix`) before optionally merging (`--auto-merge`). Respects AFK/HITL autonomy and the dependency order, and escalates a blocked build back upstream instead of editing scope. |

### Utility skills

Standalone `do-` skills -- they perform actions, like the pipeline's `do-work`, but run on their own rather than as a lane in the planning-and-build chain:

| Skill | What it does |
|---|---|
| [`do-git-workflow`](./do-git-workflow) | Enforces a branch-first Git workflow -- `type/short-description` branches, Conventional Commits with GitMoji prefixes, and pull requests opened via the `gh` CLI (ready for review by default; draft only mid-work). |
| [`do-pr-review`](./do-pr-review) | Reviews a GitHub PR diff, posts inline review comments, validates or rejects existing comments in-thread, and submits a verdict. Comment-only -- never edits code. Also runs as the review step inside `do-work`'s drain. |
| [`do-pr-fix`](./do-pr-fix) | Implements the requested changes on a reviewed PR, replies in-thread explaining each fix, runs tests/build, and pushes the commits -- the back-half of the review loop and companion to `do-pr-review`. Also runs as the fix step inside `do-work`'s drain. |

Skills load progressively: only the frontmatter `description` sits in context at all times; the `SKILL.md` body loads when the skill is triggered, and supporting files load only when referenced. Keep that in mind when adding to a skill -- bundled reference files are effectively free until used.

### How these skills chain

These four skills form a pipeline -- three `make-` lanes that produce the planning artifacts, then `do-work` to build from them. Each consumes what the lane upstream produced, and a **version lock** at every hop keeps them honest.

```
discovery ──/make-prd──▶  PRD  ──/make-tdd──▶  TDD  ──/make-issues──▶  GitHub Issues
            (WHAT / WHY)         (HOW)                (work items)            │
                                                                       /do-work
                                                                             ▼
                                                                 merged PRs (shipped code)
```

- **`/make-prd`** turns discovery material into a PRD and stamps `prd-data.meta.prd_version`.
- **`/make-tdd`** derives the TDD and **locks** it to the PRD version it was built from (`tdd-data.meta.prd_version`). Its validator refuses a TDD whose lock lags the live PRD (rule V-017).
- **`/make-issues`** refuses to run unless `prd-data.meta.prd_version == tdd-data.meta.prd_version`, then projects the TDD's capabilities into issues stamped with both versions and a per-capability fingerprint.
- **`/do-work`** refuses to build a backlog whose TDD has moved past the PRD, then claims each actionable issue, builds the slice, and opens a PR that closes it -- respecting the issue's AFK/HITL flag and its dependency order.

**Loop-back.** Change flows forward only. Amend the PRD → re-run `/make-tdd` to re-derive and re-lock → re-run `/make-issues` to reconcile → `/do-work` resumes building. You never edit scope inside an issue or skip a lane: each skill diffs rather than rewrites, preserves IDs, and reports what downstream work the change owes. When a build hits a wall, `/do-work` escalates *back* up the same chain -- a design gap to `/make-tdd`, a wrong requirement to `/make-prd` -- rather than coding around it.

**One thread, end to end:**

| Lane | Artifact | IDs |
|---|---|---|
| PRD | "Customers can check out" -- a user objective and the functional requirement under it | `UO-001`, `FR-002` |
| TDD | A Shopify checkout integration whose `satisfies: [FR-002]` | `INTG-001` |
| Issues | "Build the Shopify order-create call (per `INTG-001`)" -- meta block stamps `trace_tdd: [INTG-001]`, `trace_prd: [FR-002]`, `source_versions: {prd: 1.0, tdd: 0.1}`; labels stay human-facing (`make-issues`, `afk`/`hitl`) | issue #N |
| Build | A branch + PR implementing issue #N that `Closes #N`; the merge closes it COMPLETED and unblocks its dependents | PR, branch `feat/issue-N-order-create` |

Change `INTG-001`'s contract in the TDD and re-run `/make-issues`: the per-capability fingerprint changes, so issue #N is updated (if unstarted) or flagged (if in flight) -- and the engineer's notes in the issue's human region are never touched.

### The build loop: build → review → fix → merge

`do-work` doesn't just open a PR and stop. It **drains the backlog by default** (no flag = work every actionable issue; `--limit=<N>` caps the run, `--limit=1` does a single issue), and every PR it opens runs through an automatic **review → fix loop** before the run is done with it:

```
select next issue
   │
   ▼
build  ──▶  PR opened
   │
   ▼
review  ──▶  fix  ──▶  re-review  ──▶ … (until no Critical/Major findings, max ~2 rounds)
   │                                         │
   │ can't converge after N rounds           │ clean
   ▼                                         ▼
park for a human (label `escalated`)     ready-for-review  ──▶  merge (only with --auto-merge)
```

- **Review** is `do-pr-review` (posts inline findings, comment-only). **Fix** is `do-pr-fix` (addresses the findings, replies in-thread, pushes). They run as **independent workers** -- the reviewer never shares the builder's context, so it's genuinely a second set of eyes.
- **Merge stays manual** unless you pass `--auto-merge`; a merge closes the issue and unblocks its dependents, which is what lets a full dependency chain drain in one pass.
- A PR the loop can't get clean is **left open and labelled** for a human, never merged.

Each lane of the loop runs on the **model that fits the task** -- build and review get the strongest model (build quality is upstream of everything; bug-finding is where the top model earns its cost), fix is bounded so it runs mid-tier, and the mechanical steps run on the cheapest tier. Every default is overridable per run.

| Stage | Default model | Why |
|---|---|---|
| Build (`do-work`) | **Opus** | The quality-upstream step -- a weak build becomes review/fix churn. |
| Review (`do-pr-review`) | **Opus** | The adversarial gate -- a cheaper reviewer misses real bugs. |
| Fix (`do-pr-fix`) | **Sonnet** | Bounded: the reviewer hands it a findings list to implement. |
| Preflight / Select / Escalate / Merge | **Haiku** | Run a script or a few `gh` calls -- the cheapest tier is plenty. |

This whole loop is encoded deterministically in `do-work/workflows/drain-queue.js`, run via the Workflow tool:

```js
Workflow({ scriptPath: "<do-work>/workflows/drain-queue.js",
           args: { repo: "owner/name", skillDir: "<do-work>",
                   autoMerge: true, limit: 0, parallel: 2,
                   modelBuild: "opus", modelFix: "sonnet", effortReview: "high" } })
```

The script locates `do-pr-review` and `do-pr-fix` as siblings of `skillDir` automatically. For the full mechanics -- the worker brief, the review/merge gate, the same-identity handling, and resuming a killed run -- see [`do-work/SKILL.md`](./do-work/SKILL.md) and [`do-work/references/execution-loop.md`](./do-work/references/execution-loop.md).

## Use these skills in Claude Code

Claude Code discovers skills from the filesystem -- no upload step. Skills live in one of two places:

| Scope | Path | Available in |
|---|---|---|
| Personal | `~/.claude/skills/<skill-name>/SKILL.md` | all your projects |
| Project | `<repo>/.claude/skills/<skill-name>/SKILL.md` | that project only |

### Install

Clone this repo, then **copy** or **symlink** the skill folders you want into your skills directory.

```bash
git clone git@github.com:Unfold-Agency/skills.git
cd skills

# Ensure the personal skills directory exists:
mkdir -p ~/.claude/skills

# Personal, available everywhere -- copy into the skills directory:
cp -R make-prd ~/.claude/skills/

# ...or symlink, so repo edits are picked up live (use an absolute path):
ln -s "$(pwd)/make-prd" ~/.claude/skills/
```

To make a skill available only inside a specific project, copy it into that project's `.claude/skills/` instead:

```bash
mkdir -p /path/to/your-project/.claude/skills
cp -R make-prd /path/to/your-project/.claude/skills/
```

### Invoke

- **Directly:** type `/<skill-name>` (for example `/make-prd`).
- **Automatically:** Claude triggers a skill on its own when your request matches the skill's `description`.

### Update

```bash
cd skills
git pull
```

- **Symlinked** skills are updated by the `git pull` alone.
- **Copied** skills need to be re-copied after pulling: `cp -R make-prd ~/.claude/skills/`.

For sharing across a team or distributing many skills at once, skills can also be packaged and installed as a [Claude Code plugin](https://code.claude.com/docs/en/plugins) instead of copied by hand.

## Use these skills in the Claude apps (desktop and claude.ai)

The Claude desktop app and claude.ai use the same custom-skill feature. Skills are **uploaded as zip files** rather than read from the filesystem.

**Requirements:** a Pro, Max, Team, or Enterprise plan with code execution enabled (under **Settings → Features**). Custom skills are not available on the Free plan.

### Install

1. From this repo's root, zip the skill's folder (the zip must contain the folder with its `SKILL.md`):
   ```bash
   zip -r make-prd.zip make-prd
   ```
2. In the Claude app, open **Settings → Features**.
3. Under **Skills**, upload `make-prd.zip`.

Claude uses the skill automatically when a request matches its description. The upload takes effect in new conversations.

### Update

Re-zip the folder after pulling the latest changes, then replace the existing skill in **Settings → Features** (delete the old one and upload the new zip).

> **Note:** custom skills do **not** sync across surfaces. A skill uploaded to claude.ai is not available in Claude Code or via the API, and vice versa -- each surface is managed separately. On claude.ai, custom skills are per-user and are not shared organization-wide.

## SKILL.md requirements

Every skill needs a `SKILL.md` whose YAML frontmatter declares, at minimum, `name` and `description`:

```yaml
---
name: make-prd
description: Generate and amend PRDs from discovery material. Use when the user wants to create a requirements document, formalize requirements, or amend an existing PRD.
---

# Make a PRD

Instructions for Claude go here...
```

- **`name`** -- lowercase letters, numbers, and hyphens only; max 64 characters; cannot contain the words "claude" or "anthropic". Defaults to the directory name.
- **`description`** -- non-empty, max 1024 characters. State both **what** the skill does and **when** Claude should use it; this is all Claude sees when deciding whether to trigger the skill, so make it specific.

Claude Code supports additional optional frontmatter (invocation control, subagent execution, dynamic context). See the references below.

## Contributing

- One skill per top-level directory; keep `SKILL.md` lean and push long material into `references/`.
- Branch off `main` (`type/short-description`), use Conventional Commits, and open a pull request -- do not commit directly to `main`.
- Only install skills from sources you trust: a skill can direct Claude to run code and use tools, so review `SKILL.md`, scripts, and other bundled files before use.

## References

- [Use Skills in Claude Code](https://code.claude.com/docs/en/skills)
- [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Creating custom Skills (Claude Help Center)](https://support.claude.com/en/articles/12512198-creating-custom-skills)
- [Claude Code plugins](https://code.claude.com/docs/en/plugins)
- [Agent Skills open standard](https://agentskills.io)
