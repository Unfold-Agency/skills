export const meta = {
  name: 'do-work-drain',
  description: 'Drain the make-issues backlog: build each actionable issue in its own isolated worker, then ALWAYS review and fix the PR (do-pr-review -> do-pr-fix loop) until no blocking findings remain, optionally auto-merge on green, and re-select until the queue is dry. The orchestrator (this script) holds only the queue and one verdict per issue; every build/review/fix runs in a fresh worker context.',
  whenToUse: 'Run do-work over a backlog (drain-by-default). Each PR is reviewed and fixed automatically; pass autoMerge:true to also merge clean green PRs. Pass args.repo and args.skillDir; cap with args.limit.',
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
// autoMerge:       merge each clean green PR, unblocking dependents, then continue (default false)
// limit:           max issues processed this run; <=0 / absent = unlimited (drain all)
// maxReviewRounds: fix attempts per PR before parking it for a human (default 2)
// parallel:        workers per round, 1..3 (default 1 -- serial, the baseline)
// maxRounds:       hard cap on select rounds (default 100 -- safety backstop)
// autonomy:        which queue to drain (default "afk"; the HITL invariant never auto-builds hitl)
// model<Stage>:    per-stage model override (opus|sonnet|haiku|fable) -- see MODEL below
// effort<Stage>:   per-stage effort override (low|medium|high|xhigh|max) for build/review/fix
const A = (typeof args === 'object' && args) || {}
const REPO = A.repo
const SKILL = A.skillDir
const AUTO_MERGE = !!A.autoMerge
const PARALLEL = Math.max(1, Math.min(3, parseInt(A.parallel, 10) || 1))
const ISO = PARALLEL > 1 ? { isolation: 'worktree' } : {}
const LIMIT = parseInt(A.limit, 10) > 0 ? parseInt(A.limit, 10) : Infinity
const MAX_ROUNDS = parseInt(A.maxRounds, 10) || 100
const _mrr = parseInt(A.maxReviewRounds, 10)
const MAX_REVIEW_ROUNDS = Number.isNaN(_mrr) ? 2 : Math.max(0, _mrr)
const AUTONOMY = A.autonomy || 'afk'

const ROOT = (SKILL || '').replace(/\/+do-work\/?$/, '')
const REVIEW_SKILL = A.reviewSkillDir || `${ROOT}/do-pr-review`
const FIX_SKILL = A.fixSkillDir || `${ROOT}/do-pr-fix`

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
          trace_tdd: { type: 'array', items: { type: 'string' } },
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
  },
  required: ['issue', 'status', 'summary'],
}

// The reviewer authenticates as the SAME gh user as the builder, so GitHub forces
// its submitted event to COMMENT. blocking_open -- not the GitHub review state -- is
// the loop's control signal: the count of unresolved Critical/Major findings in the
// CURRENT code.
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
  },
  required: ['issue', 'merged'],
}

// ── prompts ─────────────────────────────────────────────────────────────
const preflightPrompt = () =>
  `Run the do-work preflight gate for ${REPO} and report the verdict.\n` +
  `Execute: python ${SKILL}/scripts/work_preflight.py --prd prd-data.yaml --tdd tdd-data.yaml --repo ${REPO} --json\n` +
  `Ensure the do-work lifecycle labels exist (create any the advisory lists as missing): ` +
  `gh label create status:doing --color 1d76db --force; gh label create escalated --color d93f0b --force.\n` +
  `Return ok=true only if the gate's top-level "ok" is true. Put the failing check (or "clear") in detail.`

const selectPrompt = () =>
  `List the actionable do-work queue for ${REPO}.\n` +
  `Execute: python ${SKILL}/scripts/select_work.py --repo ${REPO} --autonomy ${AUTONOMY} --json\n` +
  `Return the parsed actionable[] and excluded[] arrays verbatim. Do not build anything.`

const workerPrompt = (item) =>
  `You are a do-work build worker. Build EXACTLY ONE GitHub issue to a pull request, then return a verdict. Do not touch any other issue.\n\n` +
  `Repo: ${REPO}\nIssue: #${item.number} -- ${item.title || ''}\n` +
  `TDD trace: ${(item.trace_tdd || []).join(', ') || '(read it from the issue meta block)'}\n\n` +
  `Follow the do-work execution loop -- full detail in ${SKILL}/references/execution-loop.md:\n` +
  `1. Claim: gh issue edit ${item.number} --repo ${REPO} --add-assignee @me --add-label status:doing\n` +
  `2. Read: gh issue view ${item.number} --repo ${REPO} (Goal, What to build, Acceptance criteria, Test plan, and the make-issues:meta block). Read the traced TDD capability by ID in tdd-data.yaml / TDD.md, and the trace_prd requirement for the why. Respect any binding constraints (BC-).\n` +
  `3. Build ONLY this slice on a new branch <type>/issue-${item.number}-<slug> off the default branch. Conventional Commits + GitMoji, one logical change per commit.\n` +
  `4. Verify: detect and run the repo's build gate (typecheck / lint / tests -- check package.json, Makefile, pyproject.toml, CI config, CLAUDE.md) AND the issue's Test plan. Do NOT open a PR on a red gate.\n` +
  `5. git push -u origin <branch>, then open a PR using ${SKILL}/assets/pr-body-template.md: include "Closes #${item.number}", the trace mirrored from the issue meta, and the acceptance checklist. Open it ready-for-review (not draft).\n` +
  `6. NEVER edit the make-issues managed regions of the issue body; track acceptance in the PR.\n\n` +
  `If you CANNOT satisfy the issue as written (a design gap, a wrong or unsatisfiable acceptance criterion, or the issue is flagged stale), STOP: comment the reason on the issue, run gh issue edit ${item.number} --repo ${REPO} --add-label escalated, do NOT open a PR, and return status "escalated". See ${SKILL}/references/escalation-and-handback.md.\n` +
  `If the build gate stays red for reasons you cannot fix and it is not an escalation, return status "failed" with the reason in summary.\n\n` +
  `Return ONLY the verdict: issue, status (built|escalated|failed), branch, pr_url (when built), gate (e.g. "tests+lint pass"), summary (one line).`

const reviewPrompt = (v, round) =>
  `You are a code reviewer in an automated build loop. Review GitHub PR ${v.pr_url} (issue #${v.issue} in ${REPO}) and return a structured verdict. Do NOT edit code.\n\n` +
  `Follow the do-pr-review skill -- full detail in ${REVIEW_SKILL}/SKILL.md:\n` +
  `1. Resolve the PR target; gather the diff (gh pr diff) and read the surrounding code and repo conventions (CLAUDE.md) before judging.\n` +
  `2. Review the CURRENT diff across correctness, security, performance, readability, architecture/reuse. Tag each finding Critical/Major/Minor/Nit. Post NEW inline review comments on lines present in the diff; skip findings you (the same gh user) already posted on this PR.\n` +
  (round > 0
    ? `   This is RE-REVIEW round ${round}: the prior findings were addressed by a fix commit. Assess the NEW state of the code -- which blocking findings remain unfixed, plus any new ones the fix introduced.\n`
    : ``) +
  `\nIMPORTANT -- single-identity automation: the PR author is the SAME gh user as you, so GitHub will force your submitted review event to COMMENT. Do NOT treat the GitHub review state as a signal.\n` +
  `Set blocking_open = the number of unresolved CRITICAL or MAJOR findings present in the current code (count them even if you chose not to re-post a duplicate comment). List each in findings[] with severity, path, line, a one-line summary, and -- if known -- the posted inline comment's databaseId as comment_id.\n` +
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

const mergePrompt = (v) =>
  `Merge the PR for do-work issue #${v.issue} in ${REPO}, but only if it is safe, then report that it was accepted and merged.\n` +
  `PR: ${v.pr_url}\n` +
  `1. Autonomy guard: gh issue view ${v.issue} --repo ${REPO} --json labels. If it carries the "hitl" label, DO NOT merge -- return merged=false, detail "hitl: human merges".\n` +
  `2. Wait for checks: gh pr checks ${v.pr_url} --watch (bounded -- the last fix push may still be running CI). If any required check ends failing, DO NOT merge -- return merged=false, detail "checks not green".\n` +
  `3. If afk and green: gh pr merge ${v.pr_url} --repo ${REPO} --squash --delete-branch. This closes issue #${v.issue} COMPLETED and unblocks its dependents.\n` +
  `Return: issue, merged (bool), detail (use "accepted & merged" on success).`

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
    const esc = await agent(escalatePrompt(v, review, round),
      { schema: ESCALATE_SCHEMA, phase: 'Review', label: `block #${v.issue}`, model: MODEL.escalate })
    return {
      ...v, status: 'review_unresolved',
      review: { clean: false, rounds: round, blocking_open: review ? review.blocking_open : -1, escalated: !!(esc && esc.labeled) },
    }
  }
  return { ...v, review: { clean: true, rounds: round, blocking_open: 0 } }
}

// ── orchestration ───────────────────────────────────────────────────────
log(`Draining ${AUTONOMY} backlog for ${REPO} -- parallel=${PARALLEL}, autoMerge=${AUTO_MERGE}, ` +
    `limit=${LIMIT === Infinity ? 'all' : LIMIT}, reviewRounds=${MAX_REVIEW_ROUNDS}`)

phase('Preflight')
const pf = await agent(preflightPrompt(), { schema: PREFLIGHT_SCHEMA, phase: 'Preflight', label: 'preflight', model: MODEL.preflight })
if (!pf || !pf.ok) {
  log(`Preflight failed: ${pf ? pf.detail : 'no verdict'}. Stopping.`)
  return { stopped: 'preflight', detail: pf ? pf.detail : null }
}

const attempted = new Set()   // every issue touched this run -- never re-process it
const built = [], escalated = [], failed = [], merged = [], reviewUnresolved = []
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

  // Build, then ALWAYS review+fix, per issue and independently (pipeline -- no barrier
  // between build and review, so issue B can build while issue A is in review).
  // PARALLEL>1 runs builds, reviews, and fixes in isolated git worktrees so they never
  // clobber each other's working tree (the reviewer may check out the PR branch to read
  // PR-version context); callers must only set parallel>1 when the batch is file-disjoint.
  // Serial (PARALLEL===1) uses the main tree -- no worktree cost.
  phase('Build')
  const processed = (await pipeline(batch,
    item => agent(workerPrompt(item), {
      schema: VERDICT_SCHEMA, phase: 'Build', label: `build #${item.number}`,
      ...withEffort(MODEL.build, EFFORT.build), ...ISO,
    }),
    async (v) => (v && v.status === 'built' && v.pr_url) ? reviewFixLoop(v) : v
  )).filter(Boolean)

  const greens = []
  for (const v of processed) {
    if (v.status === 'review_unresolved') reviewUnresolved.push(v)
    else if (v.status === 'built') { built.push(v); if (v.pr_url && (!v.review || v.review.clean)) greens.push(v) }
    else if (v.status === 'escalated') escalated.push(v)
    else failed.push(v)
  }

  if (AUTO_MERGE && greens.length) {
    phase('Merge')
    // Merge serially -- merges mutate the default branch and back-to-back merges of
    // disjoint PRs are safe in order; concurrent merges are not. A merge unblocks
    // dependents -> loop and re-select to surface the next tier.
    for (const v of greens) {
      const m = await agent(mergePrompt(v), { schema: MERGE_SCHEMA, phase: 'Merge', label: `merge #${v.issue}`, model: MODEL.merge })
      if (m) merged.push(m)
    }
  }
}

const stopped = attempted.size >= LIMIT ? `limit (${LIMIT})`
  : rounds >= MAX_ROUNDS ? `round cap (${MAX_ROUNDS})`
    : 'queue dry'

log(`Done (${stopped}). built=${built.length} merged=${merged.filter(m => m.merged).length} ` +
    `review_unresolved=${reviewUnresolved.length} escalated=${escalated.length} failed=${failed.length}`)

return {
  stopped, rounds,
  built: built.map(v => ({ issue: v.issue, pr_url: v.pr_url, review: v.review || null, summary: v.summary })),
  merged: merged.filter(m => m.merged).map(m => m.issue),
  reviewUnresolved: reviewUnresolved.map(v => ({
    issue: v.issue, pr_url: v.pr_url,
    blocking_open: v.review ? v.review.blocking_open : null, summary: v.summary,
  })),
  escalated: escalated.map(v => ({ issue: v.issue, summary: v.summary })),
  failed: failed.map(v => ({ issue: v.issue, summary: v.summary })),
}
