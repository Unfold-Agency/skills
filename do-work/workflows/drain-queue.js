export const meta = {
  name: 'do-work-drain',
  description: 'Drain the make-issues AFK backlog: build each actionable issue in its own isolated worker, optionally auto-merge on green, and re-select until the queue is dry. The orchestrator (this script) holds only the queue and one verdict per issue; every build runs in a fresh worker context.',
  whenToUse: 'Run do-work over a whole backlog unattended (the --ralph / --auto-merge path). Pass args.repo and args.skillDir.',
  phases: [
    { title: 'Preflight' },
    { title: 'Select' },
    { title: 'Build' },
    { title: 'Merge' },
  ],
}

// ── args (the orchestrator's only inputs) ───────────────────────────────
// repo:      "owner/name"                (required)
// skillDir:  absolute path to do-work/ (required -- workers run its scripts)
// autoMerge: merge each green PR, unblocking dependents, then continue (default false)
// parallel:  workers per round, 1..3 (default 1 -- serial, the baseline)
// maxIssues: hard cap on issues built this run (default 50)
// maxRounds: hard cap on select rounds (default 100)
// autonomy:  which queue to drain (default "afk"; the HITL invariant never auto-builds hitl)
const A = (typeof args === 'object' && args) || {}
const REPO = A.repo
const SKILL = A.skillDir
const AUTO_MERGE = !!A.autoMerge
const PARALLEL = Math.max(1, Math.min(3, parseInt(A.parallel, 10) || 1))
const MAX_ISSUES = parseInt(A.maxIssues, 10) || 50
const MAX_ROUNDS = parseInt(A.maxRounds, 10) || 100
const AUTONOMY = A.autonomy || 'afk'

if (!REPO || !SKILL) {
  log('ERROR: pass args.repo ("owner/name") and args.skillDir (path to do-work/). Nothing to drain.')
  return { error: 'missing args', repo: REPO || null, skillDir: SKILL || null }
}

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

const mergePrompt = (v) =>
  `Merge the PR for do-work issue #${v.issue} in ${REPO}, but only if it is safe.\n` +
  `PR: ${v.pr_url}\n` +
  `1. Autonomy guard: gh issue view ${v.issue} --repo ${REPO} --json labels. If it carries the "hitl" label, DO NOT merge -- return merged=false, detail "hitl: human merges".\n` +
  `2. Checks guard: gh pr checks ${v.pr_url} (or gh pr view ${v.pr_url} --json statusCheckRollup). If any required check is pending or failing, DO NOT merge -- return merged=false, detail "checks not green".\n` +
  `3. If afk and green: gh pr merge ${v.pr_url} --repo ${REPO} --squash --delete-branch. This closes issue #${v.issue} COMPLETED and unblocks its dependents.\n` +
  `Return: issue, merged (bool), detail.`

// ── orchestration ───────────────────────────────────────────────────────
log(`Draining ${AUTONOMY} backlog for ${REPO} -- parallel=${PARALLEL}, autoMerge=${AUTO_MERGE}, cap=${MAX_ISSUES}`)

phase('Preflight')
const pf = await agent(preflightPrompt(), { schema: PREFLIGHT_SCHEMA, phase: 'Preflight', label: 'preflight' })
if (!pf || !pf.ok) {
  log(`Preflight failed: ${pf ? pf.detail : 'no verdict'}. Stopping.`)
  return { stopped: 'preflight', detail: pf ? pf.detail : null }
}

const attempted = new Set()   // every issue touched this run -- never re-process it
const built = [], escalated = [], failed = [], merged = []
let rounds = 0

while (built.length < MAX_ISSUES && rounds < MAX_ROUNDS) {
  rounds++
  phase('Select')
  const q = await agent(selectPrompt(), { schema: QUEUE_SCHEMA, phase: 'Select', label: `select r${rounds}` })
  const fresh = (q && q.actionable ? q.actionable : []).filter(i => !attempted.has(i.number))
  if (!fresh.length) { log(`Queue dry after ${rounds} round(s): no fresh actionable ${AUTONOMY} issues.`); break }

  const batch = fresh.slice(0, Math.min(PARALLEL, MAX_ISSUES - built.length))
  batch.forEach(i => attempted.add(i.number))
  log(`Round ${rounds}: building ${batch.map(i => '#' + i.number).join(', ')}`)

  phase('Build')
  // PARALLEL>1 builds run in isolated git worktrees so they never clobber each
  // other's working tree. Serial (PARALLEL===1) uses the main tree -- no worktree
  // cost. Callers must only set parallel>1 when the batch is file-disjoint.
  const verdicts = (await parallel(batch.map(item => () =>
    agent(workerPrompt(item), {
      schema: VERDICT_SCHEMA, phase: 'Build', label: `build #${item.number}`,
      ...(PARALLEL > 1 ? { isolation: 'worktree' } : {}),
    })
  ))).filter(Boolean)

  const greens = []
  for (const v of verdicts) {
    if (v.status === 'built') { built.push(v); if (v.pr_url) greens.push(v) }
    else if (v.status === 'escalated') escalated.push(v)
    else failed.push(v)
  }

  if (AUTO_MERGE && greens.length) {
    phase('Merge')
    // Merge serially -- merges mutate the default branch and back-to-back merges
    // of disjoint PRs are safe in order; concurrent merges are not.
    for (const v of greens) {
      const m = await agent(mergePrompt(v), { schema: MERGE_SCHEMA, phase: 'Merge', label: `merge #${v.issue}` })
      if (m) merged.push(m)
    }
    // a merge unblocks dependents -> loop and re-select to surface the next tier.
  }
}

const stopped = built.length >= MAX_ISSUES ? `issue cap (${MAX_ISSUES})`
  : rounds >= MAX_ROUNDS ? `round cap (${MAX_ROUNDS})`
    : 'queue dry'

log(`Done (${stopped}). built=${built.length} merged=${merged.filter(m => m.merged).length} ` +
    `escalated=${escalated.length} failed=${failed.length}`)

return {
  stopped, rounds,
  built: built.map(v => ({ issue: v.issue, pr_url: v.pr_url, summary: v.summary })),
  merged: merged.filter(m => m.merged).map(m => m.issue),
  escalated: escalated.map(v => ({ issue: v.issue, summary: v.summary })),
  failed: failed.map(v => ({ issue: v.issue, summary: v.summary })),
}
