#!/usr/bin/env node
/*
 * No-network unit test for the terminal acceptance gate's pure decision functions
 * in workflows/drain-queue.js -- acceptanceClean / acceptanceDebt (consistency !=
 * correctness). The gate says an issue is done only when its as-built ledger exists
 * and every acceptance criterion is 'met'; a deferred or mocked one is debt.
 *
 *   node do-work/scripts/tests/test_acceptance_gate.js
 *
 * Exit 0 = the gate decides as expected. The functions are extracted from the
 * workflow source (single source of truth) and evaluated in isolation -- the
 * surrounding orchestrator (which needs the harness globals) never runs.
 */
const fs = require('fs')
const path = require('path')
const vm = require('vm')

const SRC = path.join(__dirname, '..', '..', 'workflows', 'drain-queue.js')
const src = fs.readFileSync(SRC, 'utf8')

// Pull the named functions out of the source by their declarations, so the test
// never drifts from the implementation (`async` is prepended at the call site for
// async fns). Brace-match the body, skipping braces that live inside line/block
// comments, quoted strings, and template-literal text. A mode stack keeps template
// `${...}` interpolations counted as code (their braces balance) while a stray
// brace in a string or comment is ignored -- so the extractor stays correct even
// if such a brace is introduced later.
function extract(name) {
  const start = src.indexOf(`function ${name}(`)
  if (start < 0) throw new Error(`could not find function ${name} in ${SRC}`)
  let i = src.indexOf('{', start)
  const stack = ['brace']               // the function's own opening brace
  for (i++; i < src.length && stack.length; i++) {
    const top = stack[stack.length - 1]
    const c = src[i], d = src[i + 1]
    if (top === 'tmpl') {               // inside a template literal's text
      if (c === '\\') i++               // skip an escaped char
      else if (c === '`') stack.pop()   // end of the template literal
      else if (c === '$' && d === '{') { stack.push('interp'); i++ }  // back to code
      continue
    }
    // code mode (a 'brace' block/object or a '${}' interpolation)
    if (c === '/' && d === '/') { const nl = src.indexOf('\n', i); i = nl < 0 ? src.length : nl }
    else if (c === '/' && d === '*') { i = src.indexOf('*/', i + 2) + 1 }
    else if (c === "'" || c === '"') { for (i++; i < src.length && src[i] !== c; i++) if (src[i] === '\\') i++ }
    else if (c === '`') stack.push('tmpl')
    else if (c === '{') stack.push('brace')
    else if (c === '}') stack.pop()     // closes a brace block or an interpolation
  }
  return src.slice(start, i)            // i is one past the matched closing brace
}

const sandbox = {}
vm.createContext(sandbox)
vm.runInContext(extract('acceptanceClean') + '\n' + extract('acceptanceDebt'), sandbox)
const { acceptanceClean, acceptanceDebt } = sandbox

const failures = []
function check(name, cond) {
  console.log(`${cond ? 'ok  ' : 'FAIL'} ${name}`)
  if (!cond) failures.push(name)
}

const met = (c) => ({ criterion: c, status: 'met', evidence: 'test passes' })
const mocked = (c) => ({ criterion: c, status: 'mocked', evidence: 'FIXME(dangerously) stub' })
const deferred = (c) => ({ criterion: c, status: 'deferred', evidence: 'not built' })

// acceptanceClean: every entry 'met', and a non-empty ledger, is the only clean case.
check('all met -> acceptance-clean',
  acceptanceClean({ as_built: [met('FR-CHK-001'), met('FR-CHK-002')] }) === true)
check('a single met -> acceptance-clean',
  acceptanceClean({ as_built: [met('FR-CHK-001')] }) === true)
check('any mocked -> NOT acceptance-clean',
  acceptanceClean({ as_built: [met('a'), mocked('b')] }) === false)
check('any deferred -> NOT acceptance-clean',
  acceptanceClean({ as_built: [met('a'), deferred('b')] }) === false)
check('empty ledger -> NOT acceptance-clean (nothing demonstrated)',
  acceptanceClean({ as_built: [] }) === false)
check('missing ledger -> NOT acceptance-clean',
  acceptanceClean({}) === false)
check('null verdict -> NOT acceptance-clean (no throw)',
  acceptanceClean(null) === false)
check('non-array as_built -> NOT acceptance-clean (no throw)',
  acceptanceClean({ as_built: 'oops' }) === false)
check('a malformed entry (no status) is not met -> NOT clean',
  acceptanceClean({ as_built: [met('a'), { criterion: 'b' }] }) === false)

// acceptanceDebt: exactly the non-met entries.
check('debt = the deferred/mocked entries only',
  (() => {
    const d = acceptanceDebt({ as_built: [met('a'), mocked('b'), deferred('c'), met('d')] })
    return d.length === 2 && d[0].criterion === 'b' && d[1].criterion === 'c'
  })())
check('all-met ledger has no debt',
  acceptanceDebt({ as_built: [met('a'), met('b')] }).length === 0)
check('missing ledger -> empty debt (no throw)',
  Array.isArray(acceptanceDebt({})) && acceptanceDebt({}).length === 0)

// The clean<->debt relationship: clean iff a non-empty ledger has zero debt.
check('clean iff non-empty ledger with zero debt',
  (() => {
    const cases = [
      { as_built: [met('a')] },
      { as_built: [met('a'), mocked('b')] },
      { as_built: [] },
      {},
    ]
    return cases.every(v => {
      const clean = acceptanceClean(v)
      const ledger = Array.isArray(v.as_built) ? v.as_built : []
      return clean === (ledger.length > 0 && acceptanceDebt(v).length === 0)
    })
  })())

// ── applyAcceptanceGate: the orchestrator park/merge/follow-up wiring ─────────
// The pure decisions above feed applyAcceptanceGate, where the keystone actually
// lives: a non-clean ledger must PARK in normal mode (never a merge candidate)
// and, under --dangerously, stay a merge candidate while opening a tracked
// follow-up. Extract the async gate and run it with stubbed harness globals
// (agent/log) and stubbed prompt builders so those branches are exercised.
sandbox.acceptanceFollowupPrompt = () => 'followup-prompt'
sandbox.acceptanceParkPrompt = () => 'park-prompt'
sandbox.ESCALATE_SCHEMA = {}
sandbox.MODEL = { escalate: 'm' }
sandbox.log = () => {}
let agentCalls = []
sandbox.agent = async (_prompt, opts) => { agentCalls.push(opts && opts.label); return { labeled: true, summary: 'fu' } }
vm.runInContext('async ' + extract('applyAcceptanceGate'), sandbox)
const applyAcceptanceGate = sandbox.applyAcceptanceGate

const builtPR = (ledger) => ({ issue: 1, status: 'built', pr_url: 'https://x/1', as_built: ledger })
async function runGate(verdict, dangerous) {
  sandbox.DANGEROUS = dangerous
  agentCalls = []
  return applyAcceptanceGate(verdict)
}

;(async () => {
  // normal mode: only an all-met ledger stays a merge candidate; everything else parks.
  let r = await runGate(builtPR([met('a'), met('b')]), false)
  check('gate normal all-met -> stays built + acceptance.clean (merge candidate)',
    r.status === 'built' && r.acceptance.clean === true)
  r = await runGate(builtPR([met('a'), deferred('b')]), false)
  check('gate normal one-deferred -> parked review_unresolved (never merged)',
    r.status === 'review_unresolved' && r.acceptance.clean === false)
  r = await runGate(builtPR([met('a'), mocked('b')]), false)
  check('gate normal one-mocked -> parked review_unresolved',
    r.status === 'review_unresolved')
  r = await runGate(builtPR([]), false)
  check('gate normal empty ledger -> parked review_unresolved (no_ledger)',
    r.status === 'review_unresolved' && r.acceptance.no_ledger === true)
  r = await runGate(builtPR(undefined), false)
  check('gate normal missing ledger -> parked review_unresolved',
    r.status === 'review_unresolved')

  // --dangerously: stays a merge candidate, but every gap opens a tracked follow-up.
  r = await runGate(builtPR([met('a'), deferred('b'), mocked('c')]), true)
  check('gate dangerous with debt -> stays built + opens a follow-up',
    r.status === 'built' && r.acceptance.dangerously_proceed === true
    && r.followups.length === 1 && agentCalls.length === 1)
  r = await runGate(builtPR([]), true)
  check('gate dangerous no-ledger -> stays built + opens a follow-up (the fix)',
    r.status === 'built' && r.acceptance.no_ledger === true
    && r.followups.length === 1 && agentCalls.length === 1)
  r = await runGate(builtPR([met('a')]), true)
  check('gate dangerous all-met -> clean, no follow-up',
    r.acceptance.clean === true && agentCalls.length === 0)

  // a non-built verdict (already parked / failed) passes through untouched.
  r = await runGate({ issue: 2, status: 'review_unresolved', pr_url: 'x' }, false)
  check('gate passes a non-built verdict through unchanged',
    r.status === 'review_unresolved')

  console.log()
  if (failures.length) {
    console.log(`FAILURES: ${failures.join(', ')}`)
    process.exit(1)
  }
  console.log('acceptance gate decides as expected')
  process.exit(0)
})()
