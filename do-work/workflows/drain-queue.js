export const meta = {
  name: 'do-work-drain',
  description: 'Drain the make-issues backlog: build each actionable issue in its own isolated worker, then ALWAYS review and fix the PR (do-pr-review -> do-pr-fix loop) until no blocking findings remain, apply the terminal acceptance gate (every acceptance criterion in the worker as-built ledger must be met -- consistency != correctness), optionally auto-merge on green, and re-select until the queue is dry. The orchestrator (this script) holds only the queue and one verdict per issue; every build/review/fix runs in a fresh worker context.',
  whenToUse: 'Run do-work over a backlog (drain-by-default). Each PR is reviewed and fixed automatically; pass autoMerge:true to also merge clean green PRs, or dangerously:true for full autonomy (build AND merge every issue incl. hitl, mock blockers, never stop -- flags follow-ups). Pass args.repo and args.skillDir; cap with args.limit, scope to one phase with args.phase, or target a single issue with args.issue.',
  phases: [
    { title: 'Preflight', model: 'haiku' },
    { title: 'Select', model: 'haiku' },
    { title: 'Build', model: 'opus' },
    { title: 'Review', model: 'opus' },
    { title: 'Fix', model: 'sonnet' },
    { title: 'Merge', model: 'haiku' },
  ],
}

// ── args (the orchestrator's only inputs) ───────────────────────────────
// repo:            "owner/name"                (required)
// skillDir:        absolute path to do-work/ (required -- workers run its scripts)
// reviewSkillDir:  absolute path to do-pr-review/ (default: sibling of do-work)
// fixSkillDir:     absolute path to do-pr-fix/    (default: sibling of do-work)
// reviewToken:     bot token for the review identity (default: env GH_REVIEW_TOKEN).
//                  Set -> the reviewer authenticates as the bot and can submit a real
//                  REQUEST_CHANGES; GitHub's native review state carries the signal.
//                  Absent -> same-identity fallback (the structured blocking_open gate).
// autoMerge:       merge each clean green PR, unblocking dependents, then continue (default false)
// dangerously:     FULL AUTONOMY -- build AND merge every buildable issue (afk + hitl),
//                  resolve implementation ambiguity with best-practice defaults / mocks
//                  (an unsatisfiable criterion still escalates), merge on green CI even
//                  with unresolved review findings,
//                  open a needs-human-review follow-up issue for anything decided, and
//                  never stop for a human. Forces autonomy=any + autoMerge. Still skips
//                  make-issues stale/escalated issues. Red CI is never merged.
// limit:           max issues processed this run; <=0 / absent = unlimited (drain all)
// phase:           drain only issues in implementation phase N (the milestone
//                  "Phase N: ..."); absent = all phases. Composes with limit.
// issue:           build only this one issue number; bypasses the phase/autonomy
//                  filters but still skips a flagged/blocked/in-flight target.
//                  Takes precedence over phase.
// maxReviewRounds: fix attempts per PR before parking it for a human (default 2)
// parallel:        workers per round, 1..3 (default 1 -- serial, the baseline)
// maxRounds:       hard cap on select rounds (default 100 -- safety backstop)
// autonomy:        which queue to drain (default "afk"; the HITL invariant never auto-builds hitl)
// model<Stage>:    per-stage model override (opus|sonnet|haiku|fable) -- see MODEL below
// effort<Stage>:   per-stage effort override (low|medium|high|xhigh|max) for build/review/fix
const A = (typeof args === 'object' && args) || {}
const REPO = A.repo
const SKILL = A.skillDir
// DANGEROUS is the full-autonomy master switch: build AND merge EVERY buildable
// issue (afk + hitl), resolve implementation ambiguity with best-practice defaults and
// mocks (an unsatisfiable criterion -- a spec defect -- still escalates), merge on green
// CI even with unresolved review findings,
// and never stop for a human -- flag anything it decided as a needs-human-review
// follow-up issue and keep moving. It forces autonomy=any and autoMerge=on. It
// still skips make-issues stale/escalated issues (the spec is known out of date).
const DANGEROUS = !!A.dangerously
const AUTO_MERGE = DANGEROUS || !!A.autoMerge
const PARALLEL = Math.max(1, Math.min(3, parseInt(A.parallel, 10) || 1))
const ISO = PARALLEL > 1 ? { isolation: 'worktree' } : {}
const LIMIT = parseInt(A.limit, 10) > 0 ? parseInt(A.limit, 10) : Infinity
const PHASE = parseInt(A.phase, 10) > 0 ? parseInt(A.phase, 10) : null
const ISSUE = parseInt(A.issue, 10) > 0 ? parseInt(A.issue, 10) : null
const MAX_ROUNDS = parseInt(A.maxRounds, 10) || 100
const _mrr = parseInt(A.maxReviewRounds, 10)
const MAX_REVIEW_ROUNDS = Number.isNaN(_mrr) ? 2 : Math.max(0, _mrr)
const AUTONOMY = DANGEROUS ? 'any' : (A.autonomy || 'afk')

const ROOT = (SKILL || '').replace(/\/+do-work\/?$/, '')
const REVIEW_SKILL = A.reviewSkillDir || `${ROOT}/do-pr-review`
const FIX_SKILL = A.fixSkillDir || `${ROOT}/do-pr-fix`

// Bot review identity (optional). When a bot token is available, the review step
// authenticates as the bot so it can submit a real REQUEST_CHANGES review event
// and GitHub's native review state carries the signal. Pass it explicitly as
// args.reviewToken, or let the worker read GH_REVIEW_TOKEN from the environment.
// Absent -> the reviewer shares the builder's gh login and the loop keys off the
// structured blocking_open count (the same-identity fallback, unchanged).
const REVIEW_TOKEN = A.reviewToken || (typeof process !== 'undefined' && process.env && process.env.GH_REVIEW_TOKEN) || null
// When the token arrived as an arg, export it so the review subagent's shell can
// read $GH_REVIEW_TOKEN -- the bot-identity prompt depends on that env var. Without
// this, args.reviewToken would silently degrade to the same-identity fallback
// (and miss the fallback's "don't trust the GitHub review state" safeguard).
if (A.reviewToken && typeof process !== 'undefined' && process.env) {
  process.env.GH_REVIEW_TOKEN = A.reviewToken
}
const HAS_REVIEW_TOKEN = !!REVIEW_TOKEN

if (!REPO || !SKILL) {
  log('ERROR: pass args.repo ("owner/name") and args.skillDir (path to do-work/). Nothing to drain.')
  return { error: 'missing args', repo: REPO || null, skillDir: SKILL || null }
}

// ── per-stage model + effort ────────────────────────────────────────────
// Match the model to the task. Build and review get the strongest model -- build
// quality is upstream of everything (a weak build becomes review/fix churn), and
// bug-finding is exactly where the top model earns its cost. Fix is bounded (the
// reviewer hands it a findings list), so a mid-tier model fits. The mechanical
// agents (preflight, select, escalate, merge) run a script or a few gh calls --
// the cheapest tier is plenty. Override any of these via args.
// CAVEAT: if the CLAUDE_CODE_SUBAGENT_MODEL env var is set, it overrides ALL of
// these -- leave it unset in CI/cron or the whole loop collapses to one tier.
const MODEL = {
  preflight: A.modelPreflight || 'haiku',
  select:    A.modelSelect    || 'haiku',
  build:     A.modelBuild     || 'opus',
  review:    A.modelReview    || 'opus',
  fix:       A.modelFix       || 'sonnet',
  escalate:  A.modelEscalate  || 'haiku',
  merge:     A.modelMerge     || 'haiku',
}
const EFFORT = {
  build:  A.effortBuild  || 'high',
  review: A.effortReview || 'high',
  fix:    A.effortFix    || 'medium',
}
// Haiku rejects the effort parameter entirely (it 400s); xhigh/max are only
// accepted on the Opus/Fable tiers (Sonnet tops out at high). Attach effort only
// where the model takes it, and clamp an over-spec'd override -- e.g. effortFix
// set to xhigh while modelFix stays the default sonnet -- down to high rather
// than let it 400 mid-drain.
const TOP_EFFORT = new Set(['opus', 'fable'])
const withEffort = (model, effort) =>
  model === 'haiku' ? { model }
    : !TOP_EFFORT.has(model) && (effort === 'xhigh' || effort === 'max') ? { model, effort: 'high' }
      : { model, effort }

// ── schemas (workers return data, not prose) ────────────────────────────
const PREFLIGHT_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    ok: { type: 'boolean' },
    repo: { type: 'string' },
    detail: { type: 'string' },
  },
  required: ['ok', 'detail'],
}

const QUEUE_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    actionable: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          number: { type: 'integer' },
          title: { type: 'string' },
          autonomy: { type: 'string' },
          resumable: { type: 'boolean' },
          trace_req: { type: 'array', items: { type: 'string' } },
          feature: { type: 'string' },
        },
        required: ['number'],
      },
    },
    excluded: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: { number: { type: 'integer' }, reason: { type: 'string' } },
        required: ['number'],
      },
    },
  },
  required: ['actionable'],
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    issue: { type: 'integer' },
    status: { type: 'string', enum: ['built', 'escalated', 'failed'] },
    branch: { type: 'string' },
    pr_url: { type: 'string' },
    gate: { type: 'string' },
    summary: { type: 'string' },
    // The AS-BUILT LEDGER: one entry per acceptance criterion the issue carries,
    // filled truthfully from what the worker actually implemented. This is the
    // record the terminal acceptance gate reads (consistency != correctness): the
    // fingerprint gates prove the specs/issues/build are mutually consistent, but
    // only this ledger says whether each criterion was actually MET vs deferred or
    // mocked. A 'met' entry has real evidence (a test, a checked behavior); a
    // 'mocked' one is backed by a FIXME(dangerously) stub; a 'deferred' one was
    // not built. An issue is acceptance-clean only when every entry is 'met'.
    as_built: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          criterion: { type: 'string' },   // the acceptance criterion text or its id
          status: { type: 'string', enum: ['met', 'deferred', 'mocked'] },
          evidence: { type: 'string' },     // how it was verified, or why deferred/mocked
        },
        required: ['criterion', 'status'],
      },
    },
    // dangerous mode: best-practice defaults / mocks the worker introduced, and
    // the needs-human-review follow-up issues it opened for them.
    assumptions: { type: 'integer' },
    followups: { type: 'array', items: { type: 'string' } },
  },
  required: ['issue', 'status', 'summary'],
}

// ── terminal acceptance gate (consistency != correctness) ────────────────
// Pure decisions over the as-built ledger. The fingerprint gates upstream prove
// the specs, issues, and build are mutually CONSISTENT; they do not prove the
// shipped code actually SATISFIES the acceptance criteria. This gate closes that
// last gap by reading what the worker recorded as actually met.
//
// acceptanceClean: an issue is acceptance-clean only when its ledger exists, is
// non-empty, and every entry is 'met'. A missing/empty ledger or any 'deferred'
// or 'mocked' entry means the code does NOT demonstrably satisfy every criterion,
// so the issue is not done. This RECORDS AND GATES on what was met; it does not
// itself prove correctness.
function acceptanceClean(verdict) {
  const ledger = verdict && Array.isArray(verdict.as_built) ? verdict.as_built : []
  if (!ledger.length) return false
  return ledger.every(e => e && e.status === 'met')
}

// acceptanceDebt: the deferred/mocked entries -- the criteria the gate surfaces
// (the run summary lists them; --dangerously opens a follow-up per entry).
function acceptanceDebt(verdict) {
  const ledger = verdict && Array.isArray(verdict.as_built) ? verdict.as_built : []
  return ledger.filter(e => e && e.status !== 'met')
}

// The reviewer reviews the PR in a context independent of the builder's (a fresh
// worker that never sees the build transcript). Two identity paths:
//  * Bot token set (GH_REVIEW_TOKEN / args.reviewToken): the reviewer authenticates
//    as the bot, so it can submit a real REQUEST_CHANGES event and GitHub's native
//    review state carries the signal.
//  * No bot token (the fallback): builder and reviewer share one gh login, so GitHub
//    forces the event to COMMENT. blocking_open -- not the GitHub review state -- is
//    then the loop's control signal: the count of unresolved Critical/Major findings
//    in the CURRENT code.
const REVIEW_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    issue: { type: 'integer' },
    pr_url: { type: 'string' },
    blocking_open: { type: 'integer' },
    total_findings: { type: 'integer' },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          severity: { type: 'string' },
          path: { type: 'string' },
          line: { type: 'integer' },
          summary: { type: 'string' },
          comment_id: { type: 'integer' },
        },
        required: ['severity', 'summary'],
      },
    },
    github_event: { type: 'string' },
    summary: { type: 'string' },
  },
  required: ['issue', 'blocking_open', 'summary'],
}

const FIX_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    issue: { type: 'integer' },
    pr_url: { type: 'string' },
    commits_pushed: { type: 'integer' },
    addressed: { type: 'integer' },
    rejected: { type: 'integer' },
    replies_posted: { type: 'integer' },
    verification_passed: { type: 'boolean' },
    summary: { type: 'string' },
  },
  required: ['issue', 'summary'],
}

const ESCALATE_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    issue: { type: 'integer' },
    labeled: { type: 'boolean' },
    summary: { type: 'string' },
  },
  required: ['issue'],
}

const MERGE_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    issue: { type: 'integer' },
    merged: { type: 'boolean' },
    detail: { type: 'string' },
    followup: { type: 'string' },   // dangerous mode: follow-up issue URL on a red-CI skip
  },
  required: ['issue', 'merged'],
}

// ── prompts ─────────────────────────────────────────────────────────────
const preflightPrompt = () =>
  `Run the do-work preflight gate for ${REPO} and report the verdict.\n` +
  `Execute: python ${SKILL}/scripts/work_preflight.py --spec-dir docs/specs --repo ${REPO} --json\n` +
  `Ensure the do-work lifecycle labels exist (create any the advisory lists as missing): ` +
  `gh label create status:doing --color 1d76db --force; gh label create escalated --color d93f0b --force; ` +
  `gh label create needs-human-review --color fbca04 --force.\n` +
  `Return ok=true only if the gate's top-level "ok" is true. Put the failing check (or "clear") in detail.`

const selectCmd =
  `python ${SKILL}/scripts/select_work.py --repo ${REPO} --autonomy ${AUTONOMY}` +
  (PHASE !== null ? ` --phase ${PHASE}` : ``) +
  (ISSUE !== null ? ` --issue ${ISSUE}` : ``) + ` --json`
const selectPrompt = () =>
  `List the actionable do-work queue for ${REPO}.\n` +
  `Execute: ${selectCmd}\n` +
  `Return the parsed actionable[] and excluded[] arrays verbatim. Do not build anything.`

const workerPrompt = (item, dangerous) =>
  `You are a do-work build worker. Build EXACTLY ONE GitHub issue to a pull request, then return a verdict. Do not touch any other issue.\n\n` +
  `Repo: ${REPO}\nIssue: #${item.number} -- ${item.title || ''}\n` +
  `Requirement: ${(item.trace_req || []).join(', ') || '(read it from the issue meta block)'}\n\n` +
  (dangerous
    ? `MODE: --dangerously. Full autonomy: do NOT stop for a human and do NOT escalate -- EXCEPT an unsatisfiable acceptance criterion (a spec defect), which still escalates and stops this issue. Build this issue (it may be hitl -- build it anyway).\n\n`
    : ``) +
  `Follow the do-work execution loop -- full detail in ${SKILL}/references/execution-loop.md:\n` +
  `1. Claim: gh issue edit ${item.number} --repo ${REPO} --add-assignee @me --add-label status:doing\n` +
  `2. Read: gh issue view ${item.number} --repo ${REPO} (Goal, What to build, Acceptance criteria, Test plan, and the make-issues:meta block). The issue is self-contained -- the requirement, its EARS acceptance criteria, and a governing-ADR snippet are embedded. Read the full ADR in docs/specs/decisions/ by its trace_adr only if you need the rationale; do NOT re-derive or edit the spec.\n` +
  `3. Build ONLY this slice on a new branch <type>/issue-${item.number}-<slug> off the default branch. Conventional Commits + GitMoji, one logical change per commit.\n` +
  `4. Verify: detect and run the repo's build gate (typecheck / lint / tests -- check package.json, Makefile, pyproject.toml, CI config, CLAUDE.md) AND the issue's Test plan. Do NOT open a PR on a red gate.\n` +
  `5. git push -u origin <branch>, then open a PR using ${SKILL}/assets/pr-body-template.md: include "Closes #${item.number}", the trace mirrored from the issue meta, the acceptance checklist, and the "## As-built" ledger (one row per acceptance criterion: met / deferred / mocked, with evidence). Open it ready-for-review (not draft).\n` +
  `6. NEVER edit the make-issues managed regions of the issue body; track acceptance in the PR.\n\n` +
  `AS-BUILT LEDGER (required in every verdict). For EACH acceptance criterion the issue carries, record one entry in as_built: {criterion: "<text or id>", status: "met" | "deferred" | "mocked", evidence: "<how you verified it, or why it is deferred/mocked>"}. Be truthful from what you ACTUALLY implemented: "met" needs real evidence (a passing test, a checked behavior), "mocked" means it is backed by a FIXME(dangerously) stub, "deferred" means it was not built. The orchestrator gates on this -- an honest "deferred"/"mocked" is right; a "met" that was not really met is a defect.\n\n` +
  (dangerous
    ? `RESOLVE IMPLEMENTATION AMBIGUITY; ESCALATE A SPEC DEFECT. If the gap is implementation ambiguity (a wiring choice, a default the spec leaves open) or a design gap you can reasonably resolve -- pick the best-practice resolution and build it. If the slice needs a missing external (an API, seed data, a credential, an upstream service), create a CLEARLY-MARKED mock/placeholder (a fixture, a stub module, env defaults) tagged with a "FIXME(dangerously)" comment so the gate passes against the mock. BUT if an acceptance criterion is genuinely UNSATISFIABLE as written -- a contradiction in the WHAT, not an implementation choice -- that is a spec defect: comment the reason, run gh issue edit ${item.number} --repo ${REPO} --add-label escalated, open no PR, and return status "escalated", even in this mode. Never edit the specs or the issue's managed scope -- you resolve IMPLEMENTATION ambiguity and mock MISSING EXTERNALS, you do not rewrite or paper over requirements.\n` +
      `FLAG EACH DECISION. For every best-practice default you chose and every mock/placeholder you created, open a follow-up issue: gh issue create --repo ${REPO} --label needs-human-review --title "Follow-up: <what> on #${item.number}" --body "<what you assumed/mocked, where in the code, and why>". Add a PR comment linking each follow-up. List each assumption/mock in an "Assumptions & mocks" section of the PR body.\n` +
      `Return status "escalated" ONLY for an unsatisfiable spec defect (above). Otherwise, if NO green build is possible even with mocks, open a needs-human-review follow-up describing the blocker and return status "failed" (do NOT add the escalated label, do NOT stop the run).\n` +
      `Return ONLY the verdict: issue, status (built|escalated|failed), branch, pr_url (when built), gate, as_built (the ledger -- one entry per acceptance criterion), assumptions (count of defaults/mocks), followups (the follow-up issue URLs), summary (one line).`
    : `If you CANNOT satisfy the issue as written (a design gap, a wrong or unsatisfiable acceptance criterion, or the issue is flagged stale), STOP: comment the reason on the issue, run gh issue edit ${item.number} --repo ${REPO} --add-label escalated, do NOT open a PR, and return status "escalated". See ${SKILL}/references/escalation-and-handback.md.\n` +
      `If the build gate stays red for reasons you cannot fix and it is not an escalation, return status "failed" with the reason in summary.\n\n` +
      `Return ONLY the verdict: issue, status (built|escalated|failed), branch, pr_url (when built), gate (e.g. "tests+lint pass"), as_built (the ledger -- one entry per acceptance criterion), summary (one line).`)

const reviewPrompt = (v, round) =>
  `You are a code reviewer in an automated build loop. Review GitHub PR ${v.pr_url} (issue #${v.issue} in ${REPO}) and return a structured verdict. Do NOT edit code.\n\n` +
  (HAS_REVIEW_TOKEN
    ? `REVIEW IDENTITY: a bot review token is set. Authenticate the gh CLI as the bot for this review (export GH_TOKEN="$GH_REVIEW_TOKEN" for your gh calls, or use \`gh ... --token "$GH_REVIEW_TOKEN"\`). Because you are NOT the PR author, GitHub accepts a real review event -- submit REQUEST_CHANGES when there is any Critical/Major finding, COMMENT for Minor/Nit only, APPROVE when clean. GitHub's native review state then carries the signal.\n\n`
    : ``) +
  `Follow the do-pr-review skill -- full detail in ${REVIEW_SKILL}/SKILL.md:\n` +
  `1. Resolve the PR target; gather the diff (gh pr diff) and read the surrounding code and repo conventions (CLAUDE.md) before judging.\n` +
  `2. Review the CURRENT diff across correctness, security, performance, readability, architecture/reuse. Tag each finding Critical/Major/Minor/Nit. Post NEW inline review comments on lines present in the diff; skip findings already posted on this PR.\n` +
  (round > 0
    ? `   This is RE-REVIEW round ${round}: the prior findings were addressed by a fix commit. Assess the NEW state of the code -- which blocking findings remain unfixed, plus any new ones the fix introduced.\n`
    : ``) +
  (HAS_REVIEW_TOKEN
    ? `\nSet blocking_open = the number of unresolved CRITICAL or MAJOR findings present in the current code, and set github_event to the event you submitted (REQUEST_CHANGES when blocking_open > 0).\n`
    : `\nIMPORTANT -- same-identity fallback (no bot token): the PR author is the SAME gh user as you, so GitHub will force your submitted review event to COMMENT. Do NOT treat the GitHub review state as a signal.\n` +
      `Set blocking_open = the number of unresolved CRITICAL or MAJOR findings present in the current code (count them even if you chose not to re-post a duplicate comment).\n`) +
  `List each blocking finding in findings[] with severity, path, line, a one-line summary, and -- if known -- the posted inline comment's databaseId as comment_id.\n` +
  `Return ONLY: issue, pr_url, blocking_open, total_findings, findings[], github_event (what you submitted), summary (one line).`

const fixPrompt = (v, findings) =>
  `You are a fixer in an automated build loop. Address the review findings on GitHub PR ${v.pr_url} (issue #${v.issue} in ${REPO}), then return a structured verdict. You EDIT code and push.\n\n` +
  `Findings to address (from the reviewer):\n${JSON.stringify(findings || [], null, 2)}\n\n` +
  `Follow the do-pr-fix skill -- full detail in ${FIX_SKILL}/SKILL.md, with ONE override:\n` +
  `* OVERRIDE: do-pr-fix normally skips threads "authored solely by $ME". In THIS automated run the reviewer authenticates as the SAME gh user as you, so DO NOT skip same-user threads -- the reviewer's comments ARE your work list.\n` +
  `1. gh pr checkout ${v.pr_url}. Enumerate unresolved review threads (the GraphQL query in Step 3), INCLUDING same-user threads, so you have each thread's id and first comment's databaseId.\n` +
  `2. For each finding above: if valid, implement the change (Edit/Write); if genuinely invalid, make no edit and queue a rejection.\n` +
  `3. Run the repo build gate (tests, then build/lint). Do NOT push on a red gate -- return verification_passed=false with the reason in summary.\n` +
  `4. Commit grouped by area (emoji-first Conventional Commits, Co-Authored-By trailer), then git push to the PR branch. Never force-push.\n` +
  `5. ALWAYS reply inline in each addressed thread -- "Fixed. <what changed and how>." or "Rejected. <reason>." -- referencing the commit SHA where useful. This inline reply is REQUIRED for every comment you act on.\n` +
  `6. Resolve every thread you addressed (the resolveReviewThread mutation on each thread node id) -- the do-pr-fix --resolve behaviour.\n` +
  `Return ONLY: issue, pr_url, commits_pushed, addressed, rejected, replies_posted, verification_passed, summary (one line).`

const escalatePrompt = (v, review, round) =>
  `The automated review loop could not clear the blocking findings on PR ${v.pr_url} (issue #${v.issue} in ${REPO}) after ${round} fix round(s). Park it for a human.\n` +
  `1. Comment on the PR (gh pr comment ${v.pr_url} --body ...) summarising the unresolved blocking findings: ${review ? review.blocking_open : 'unknown'} remaining -- ${review ? (review.summary || '').replace(/\n/g, ' ') : 'no review verdict'}.\n` +
  `2. Label the issue so it leaves the actionable queue: gh issue edit ${v.issue} --repo ${REPO} --add-label escalated\n` +
  `3. Leave the PR OPEN -- do NOT merge it and do NOT close the issue.\n` +
  `Return: issue, labeled (true if the escalated label was added), summary (one line).`

// --dangerously: instead of parking an unconverged PR, flag the residual findings
// as a follow-up issue and let it proceed to the merge step (which still gates on CI).
const reviewFollowupPrompt = (v, review, round) =>
  `In --dangerously mode the review loop could not clear all blocking findings on PR ${v.pr_url} (issue #${v.issue} in ${REPO}) after ${round} fix round(s). Do NOT park it and do NOT add the escalated label -- flag and proceed.\n` +
  `1. Open a follow-up issue: gh issue create --repo ${REPO} --label needs-human-review --title "Follow-up: unresolved review findings on #${v.issue}" --body "PR ${v.pr_url} was merged under --dangerously with ${review ? review.blocking_open : 'unknown'} unresolved Critical/Major finding(s): ${review ? (review.summary || '').replace(/\n/g, ' ') : 'see PR'}. Human review needed."\n` +
  `2. Comment on the PR linking the follow-up issue.\n` +
  `Return: issue, labeled (false -- this mode does not escalate), summary (the follow-up issue URL).`

// Terminal acceptance gate, NORMAL mode: the review converged, but the as-built
// ledger has deferred/mocked criteria, so the issue is NOT acceptance-clean. Park
// it like an unconverged review -- the ledger is the reason -- and never merge it
// as if complete.
const acceptanceParkPrompt = (v, debt) =>
  `PR ${v.pr_url} (issue #${v.issue} in ${REPO}) passed review but is NOT acceptance-clean: ${debt.length} acceptance criterion/criteria were deferred or mocked, so the shipped code does not yet satisfy the issue as written. Park it for a human.\n` +
  `As-built debt:\n${debt.map(e => `  - [${e.status}] ${e.criterion}${e.evidence ? ` -- ${e.evidence}` : ''}`).join('\n')}\n` +
  `1. Comment on the PR (gh pr comment ${v.pr_url} --body ...) listing the deferred/mocked criteria above as the reason it is not done.\n` +
  `2. Label the issue so it leaves the actionable queue: gh issue edit ${v.issue} --repo ${REPO} --add-label needs-human-review\n` +
  `3. Leave the PR OPEN -- do NOT merge it and do NOT close the issue.\n` +
  `Return: issue, labeled (true if the label was added), summary (one line naming the unmet criteria count).`

// Terminal acceptance gate, --dangerously: the ledger IS the debt record. The PR
// may still merge (on green CI), but every deferred/mocked criterion gets its own
// needs-human-review follow-up so the gap is tracked.
const acceptanceFollowupPrompt = (v, debt) =>
  `In --dangerously mode PR ${v.pr_url} (issue #${v.issue} in ${REPO}) will merge on green CI, but its as-built ledger has ${debt.length} deferred/mocked acceptance criterion/criteria. Open a needs-human-review follow-up for EACH so the debt is tracked, then let it proceed.\n` +
  `Deferred/mocked criteria:\n${debt.map(e => `  - [${e.status}] ${e.criterion}${e.evidence ? ` -- ${e.evidence}` : ''}`).join('\n')}\n` +
  `For each criterion above: gh issue create --repo ${REPO} --label needs-human-review --title "Follow-up: acceptance criterion <met/mocked/deferred> on #${v.issue}" --body "PR ${v.pr_url} merged under --dangerously without meeting: <criterion>. Status: <deferred|mocked>. Evidence/reason: <evidence>. Human review needed to confirm or build it."\n` +
  `Add one PR comment linking the follow-ups. Return: issue, labeled (false -- this mode does not park), summary (the follow-up issue URLs, comma-separated).`

const mergePrompt = (v, dangerous) =>
  `Merge the PR for do-work issue #${v.issue} in ${REPO}, but only if it is safe, then report that it was accepted and merged.\n` +
  `PR: ${v.pr_url}\n` +
  (dangerous
    ? `1. --dangerously: there is NO autonomy guard. Merge this PR even if the issue is hitl.\n` +
      `2. Wait for checks: gh pr checks ${v.pr_url} --watch (bounded -- the last fix push may still be running CI). If any required check ends FAILING, do NOT merge a red build (it would break the default branch): open a follow-up issue (gh issue create --repo ${REPO} --label needs-human-review --title "Follow-up: red CI on #${v.issue}" --body "PR ${v.pr_url} could not go green under --dangerously; left open for a human."), leave the PR OPEN, and return merged=false, detail "ci red: flagged for follow-up", followup=<the follow-up issue URL>.\n` +
      `3. If checks are green: gh pr merge ${v.pr_url} --repo ${REPO} --squash --delete-branch (merge it even with unresolved review findings -- those were already flagged as follow-ups). This closes issue #${v.issue} COMPLETED and unblocks its dependents.\n` +
      `Return: issue, merged (bool), detail (use "accepted & merged" on success), followup (URL when a red-CI follow-up was opened).`
    : `1. Autonomy guard: gh issue view ${v.issue} --repo ${REPO} --json labels. If it carries the "hitl" label, DO NOT merge -- return merged=false, detail "hitl: human merges".\n` +
      `2. Wait for checks: gh pr checks ${v.pr_url} --watch (bounded -- the last fix push may still be running CI). If any required check ends failing, DO NOT merge -- return merged=false, detail "checks not green".\n` +
      `3. If afk and green: gh pr merge ${v.pr_url} --repo ${REPO} --squash --delete-branch. This closes issue #${v.issue} COMPLETED and unblocks its dependents.\n` +
      `Return: issue, merged (bool), detail (use "accepted & merged" on success).`)

// ── review -> fix loop (runs on every built PR) ─────────────────────────
// Build -> review -> fix -> re-review, repeating until no blocking (Critical/Major)
// findings remain or MAX_REVIEW_ROUNDS fix attempts are spent. blocking_open is the
// control signal (see REVIEW_SCHEMA). If it can't converge, park the PR for a human.
async function reviewFixLoop(v) {
  let round = 0
  let review = await agent(reviewPrompt(v, round),
    { schema: REVIEW_SCHEMA, phase: 'Review', label: `review #${v.issue}`, ...withEffort(MODEL.review, EFFORT.review), ...ISO })
  while (review && review.blocking_open > 0 && round < MAX_REVIEW_ROUNDS) {
    round++
    const fix = await agent(fixPrompt(v, review.findings || []),
      { schema: FIX_SCHEMA, phase: 'Fix', label: `fix #${v.issue} r${round}`, ...withEffort(MODEL.fix, EFFORT.fix), ...ISO })
    // A fix that fails its build gate pushes nothing, so re-reviewing would just
    // re-find the same blocking findings and burn another expensive round. Stop
    // and park it for a human instead.
    if (fix && fix.verification_passed === false) {
      review = { ...review, summary: `fix could not pass the build gate: ${fix.summary || 'gate stayed red'}` }
      break
    }
    review = await agent(reviewPrompt(v, round),
      { schema: REVIEW_SCHEMA, phase: 'Review', label: `re-review #${v.issue} r${round}`, ...withEffort(MODEL.review, EFFORT.review), ...ISO })
  }
  if (!review || review.blocking_open > 0) {
    // --dangerously: do NOT park. Flag the residual findings as a follow-up issue and
    // keep the verdict 'built' so it stays a merge candidate (CI is still the gate).
    if (DANGEROUS) {
      const fu = await agent(reviewFollowupPrompt(v, review, round),
        { schema: ESCALATE_SCHEMA, phase: 'Review', label: `flag #${v.issue}`, model: MODEL.escalate })
      return {
        ...v,   // status stays 'built'
        review: { clean: false, rounds: round, blocking_open: review ? review.blocking_open : -1, dangerously_proceed: true },
        followups: [...(v.followups || []), ...(fu && fu.summary ? [fu.summary] : [])],
      }
    }
    const esc = await agent(escalatePrompt(v, review, round),
      { schema: ESCALATE_SCHEMA, phase: 'Review', label: `block #${v.issue}`, model: MODEL.escalate })
    return {
      ...v, status: 'review_unresolved',
      review: { clean: false, rounds: round, blocking_open: review ? review.blocking_open : -1, escalated: !!(esc && esc.labeled) },
    }
  }
  return { ...v, review: { clean: true, rounds: round, blocking_open: 0 } }
}

// ── terminal acceptance gate (runs after review, before merge) ───────────
// consistency != correctness: the review loop clears Critical/Major findings,
// but an issue is only DONE when every acceptance criterion was actually met.
// This reads the worker's as-built ledger and gates on it.
//  * acceptance-clean (every entry 'met') -> unchanged; proceed to merge.
//  * NOT acceptance-clean (any deferred/mocked, or no ledger):
//      - normal mode: park it like an unconverged review (status 'review_unresolved')
//        with the ledger as the reason; never merged as if complete.
//      - --dangerously: open a needs-human-review follow-up per deferred/mocked
//        entry (the ledger is the debt record) and let it stay a merge candidate.
async function applyAcceptanceGate(v) {
  // Only built PRs that survived review reach the gate; everything else passes through.
  if (!v || v.status !== 'built' || !v.pr_url) return v
  if (acceptanceClean(v)) {
    return { ...v, acceptance: { clean: true, debt: 0 } }
  }
  const debt = acceptanceDebt(v)
  const hasLedger = Array.isArray(v.as_built) && v.as_built.length > 0
  if (DANGEROUS) {
    // The ledger is the debt record: merge anyway (CI still gates), but track each gap.
    if (debt.length) {
      const fu = await agent(acceptanceFollowupPrompt(v, debt),
        { schema: ESCALATE_SCHEMA, phase: 'Review', label: `accept-debt #${v.issue}`, model: MODEL.escalate })
      return {
        ...v,   // status stays 'built' -- still a merge candidate under --dangerously
        acceptance: { clean: false, debt: debt.length, dangerously_proceed: true },
        followups: [...(v.followups || []), ...(fu && fu.summary ? [fu.summary] : [])],
      }
    }
    // No ledger at all under --dangerously: the worst case (acceptance not
    // demonstrated at all). Open a single follow-up so it is tracked like any
    // other acceptance debt, not merged on green CI with only a summary line.
    const fu = await agent(acceptanceFollowupPrompt(v, [{ status: 'deferred',
        criterion: '(no as-built ledger)', evidence: 'worker returned no as_built entries; acceptance not demonstrated' }]),
      { schema: ESCALATE_SCHEMA, phase: 'Review', label: `accept-debt #${v.issue}`, model: MODEL.escalate })
    return {
      ...v,   // status stays 'built' -- still a merge candidate under --dangerously
      acceptance: { clean: false, debt: 0, no_ledger: true, dangerously_proceed: true },
      followups: [...(v.followups || []), ...(fu && fu.summary ? [fu.summary] : [])],
    }
  }
  // Normal mode: not acceptance-clean -> park it like an unconverged review.
  const reason = hasLedger
    ? `${debt.length} acceptance criterion/criteria deferred or mocked`
    : `no as-built ledger -- acceptance not demonstrated`
  const park = await agent(acceptanceParkPrompt(v, hasLedger ? debt : [{ status: 'deferred', criterion: '(no ledger returned)', evidence: 'worker returned no as_built entries' }]),
    { schema: ESCALATE_SCHEMA, phase: 'Review', label: `accept-park #${v.issue}`, model: MODEL.escalate })
  return {
    ...v, status: 'review_unresolved',
    acceptance: { clean: false, debt: debt.length, no_ledger: !hasLedger, parked: !!(park && park.labeled), reason },
    review: { ...(v.review || {}), acceptance_parked: true },
  }
}

// ── orchestration ───────────────────────────────────────────────────────
if (DANGEROUS) {
  log(`⚠️  --dangerously: building AND merging EVERY buildable issue (afk + hitl) for ${REPO}, ` +
      `resolving blockers with best-practice defaults / mocks, merging on green CI even with ` +
      `unresolved review findings, opening needs-human-review follow-ups, and NEVER stopping for a ` +
      `human. Red CI is never merged. make-issues stale/escalated issues are still skipped.`)
}
log(`Draining ${AUTONOMY} backlog for ${REPO} -- parallel=${PARALLEL}, autoMerge=${AUTO_MERGE}, ` +
    `${DANGEROUS ? 'DANGEROUS, ' : ''}` +
    `limit=${LIMIT === Infinity ? 'all' : LIMIT}, ` +
    `${ISSUE !== null ? `issue=#${ISSUE}, ` : PHASE !== null ? `phase=${PHASE}, ` : ``}` +
    `reviewRounds=${MAX_REVIEW_ROUNDS}`)

phase('Preflight')
const pf = await agent(preflightPrompt(), { schema: PREFLIGHT_SCHEMA, phase: 'Preflight', label: 'preflight', model: MODEL.preflight })
if (!pf || !pf.ok) {
  log(`Preflight failed: ${pf ? pf.detail : 'no verdict'}. Stopping.`)
  return { stopped: 'preflight', detail: pf ? pf.detail : null }
}

const attempted = new Set()   // every issue touched this run -- never re-process it
const built = [], escalated = [], failed = [], merged = [], reviewUnresolved = []
// --dangerously merges HITL work (visual/brand, security, data-migration, money)
// with no human before the merge. The manifest is the typed record of which HITL
// issues this run will build+merge unattended, surfaced up front and in the summary.
const hitlManifest = []
let rounds = 0

while (attempted.size < LIMIT && rounds < MAX_ROUNDS) {
  rounds++
  phase('Select')
  const q = await agent(selectPrompt(), { schema: QUEUE_SCHEMA, phase: 'Select', label: `select r${rounds}`, model: MODEL.select })
  const fresh = (q && q.actionable ? q.actionable : []).filter(i => !attempted.has(i.number))
  if (!fresh.length) { log(`Queue dry after ${rounds} round(s): no fresh actionable ${AUTONOMY} issues.`); break }

  const remaining = LIMIT === Infinity ? fresh.length : LIMIT - attempted.size
  const batch = fresh.slice(0, Math.max(0, Math.min(PARALLEL, remaining)))
  if (!batch.length) break
  batch.forEach(i => attempted.add(i.number))
  log(`Round ${rounds}: building ${batch.map(i => '#' + i.number).join(', ')}`)
  if (DANGEROUS) {
    // Typed HITL auto-merge manifest: name the human-in-the-loop work this run
    // will merge with no human before the merge, so the operator sees the blast
    // radius. (autonomy='any' under --dangerously, so HITL items reach the batch.)
    const hitl = batch.filter(i => i.autonomy === 'hitl')
    for (const i of hitl) {
      hitlManifest.push({ issue: i.number, title: i.title || '', feature: i.feature || '' })
      log(`  ⚠️  HITL auto-merge: #${i.number} ${i.title || ''}${i.feature ? ` [${i.feature}]` : ''}`)
    }
  }

  // Build, then ALWAYS review+fix, per issue and independently (pipeline -- no barrier
  // between build and review, so issue B can build while issue A is in review).
  // PARALLEL>1 runs builds, reviews, and fixes in isolated git worktrees so they never
  // clobber each other's working tree (the reviewer may check out the PR branch to read
  // PR-version context); callers must only set parallel>1 when the batch is file-disjoint.
  // Serial (PARALLEL===1) uses the main tree -- no worktree cost.
  phase('Build')
  const processed = (await pipeline(batch,
    item => agent(workerPrompt(item, DANGEROUS), {
      schema: VERDICT_SCHEMA, phase: 'Build', label: `build #${item.number}`,
      ...withEffort(MODEL.build, EFFORT.build), ...ISO,
    }),
    // Review -> fix to clear Critical/Major findings, THEN the terminal acceptance
    // gate (consistency != correctness): a review-clean PR whose as-built ledger has
    // deferred/mocked criteria is not done. A PR parked by review never reaches the
    // gate (it is already review_unresolved); a review-clean one does.
    async (v) => {
      if (!(v && v.status === 'built' && v.pr_url)) return v
      const reviewed = await reviewFixLoop(v)
      return applyAcceptanceGate(reviewed)
    }
  )).filter(Boolean)

  const greens = []
  for (const v of processed) {
    if (v.status === 'review_unresolved') reviewUnresolved.push(v)
    // Under --dangerously every built PR is a merge candidate (an unconverged review
    // was already flagged as a follow-up); CI is still the gate inside the merge step.
    else if (v.status === 'built') { built.push(v); if (v.pr_url && (DANGEROUS || !v.review || v.review.clean)) greens.push(v) }
    else if (v.status === 'escalated') escalated.push(v)
    else failed.push(v)
  }

  if (AUTO_MERGE && greens.length) {
    phase('Merge')
    // Merge serially -- merges mutate the default branch and back-to-back merges of
    // disjoint PRs are safe in order; concurrent merges are not. A merge unblocks
    // dependents -> loop and re-select to surface the next tier.
    for (const v of greens) {
      const m = await agent(mergePrompt(v, DANGEROUS), { schema: MERGE_SCHEMA, phase: 'Merge', label: `merge #${v.issue}`, model: MODEL.merge })
      if (m) merged.push(m)
    }
  }
}

const stopped = attempted.size >= LIMIT ? `limit (${LIMIT})`
  : rounds >= MAX_ROUNDS ? `round cap (${MAX_ROUNDS})`
    : 'queue dry'

// --dangerously: every needs-human-review follow-up opened this run (worker
// assumptions/mocks, unresolved review findings merged anyway, acceptance-debt
// follow-ups, red-CI skips).
const followups = [
  ...built.flatMap(v => v.followups || []),
  ...failed.flatMap(v => v.followups || []),
  ...merged.map(m => m.followup).filter(Boolean),
]

// Acceptance summary (consistency != correctness): of every PR that reached the
// terminal gate (built + review-clean + acceptance-clean ones, plus the
// dangerously-proceeded ones that merged with debt, plus the normal-mode ones
// parked for unmet criteria), how many shipped fully as-spec vs with deferred/
// mocked criteria. The as-built ledgers ARE the debt record.
const gated = [...built, ...reviewUnresolved]
const acceptanceFullyMet = gated.filter(v => v.acceptance && v.acceptance.clean)
const acceptanceWithDebt = gated.filter(v => v.acceptance && !v.acceptance.clean)
const acceptanceParked = reviewUnresolved.filter(v => v.acceptance && v.acceptance.parked != null)
const acceptanceSummary = {
  fully_met: acceptanceFullyMet.length,
  with_deferred_or_mocked: acceptanceWithDebt.length,
  parked_for_unmet_acceptance: acceptanceParked.length,
  details: acceptanceWithDebt.map(v => ({
    issue: v.issue, pr_url: v.pr_url || null,
    debt: v.acceptance.debt, no_ledger: !!v.acceptance.no_ledger,
    merged_anyway: !!v.acceptance.dangerously_proceed,
  })),
}

log(`Done (${stopped}). built=${built.length} merged=${merged.filter(m => m.merged).length} ` +
    `review_unresolved=${reviewUnresolved.length} escalated=${escalated.length} failed=${failed.length}` +
    `${DANGEROUS ? ` followups=${followups.length}` : ''}`)
log(`Acceptance gate: ${acceptanceSummary.fully_met} fully met as-spec, ` +
    `${acceptanceSummary.with_deferred_or_mocked} with deferred/mocked criteria` +
    `${acceptanceSummary.parked_for_unmet_acceptance ? ` (${acceptanceSummary.parked_for_unmet_acceptance} parked for unmet acceptance)` : ''}.`)

return {
  stopped, rounds, dangerous: DANGEROUS,
  built: built.map(v => ({
    issue: v.issue, pr_url: v.pr_url, review: v.review || null,
    acceptance: v.acceptance || null, summary: v.summary,
    ...(v.assumptions ? { assumptions: v.assumptions } : {}),
  })),
  merged: merged.filter(m => m.merged).map(m => m.issue),
  reviewUnresolved: reviewUnresolved.map(v => ({
    issue: v.issue, pr_url: v.pr_url,
    blocking_open: v.review ? v.review.blocking_open : null,
    acceptance: v.acceptance || null, summary: v.summary,
  })),
  escalated: escalated.map(v => ({ issue: v.issue, summary: v.summary })),
  failed: failed.map(v => ({ issue: v.issue, summary: v.summary })),
  acceptanceSummary,
  ...(DANGEROUS ? { followups, hitlAutoMergeManifest: hitlManifest } : {}),
}
