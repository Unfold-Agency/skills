#!/usr/bin/env node
/*
 * No-network unit test for the per-run issue cap in workflows/drain-queue.js --
 * resolveLimit. The default is ONE issue (a bounded, observable run); draining the
 * whole actionable queue is the explicit opt-in noLimit:true / limit:0.
 *
 *   node do-work/scripts/tests/test_drain_limit.js
 *
 * Exit 0 = the cap resolves as expected. The function is extracted from the workflow
 * source (single source of truth) and evaluated in isolation -- the surrounding
 * orchestrator (which needs the harness globals) never runs.
 */
const fs = require('fs')
const path = require('path')
const vm = require('vm')

const SRC = path.join(__dirname, '..', '..', 'workflows', 'drain-queue.js')
const src = fs.readFileSync(SRC, 'utf8')

// Pull a named function out of the source by its declaration, brace-matching the body
// while skipping braces inside line/block comments, strings, and template text. Same
// extractor as test_acceptance_gate.js, so the test never drifts from the source.
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
vm.runInContext(extract('resolveLimit'), sandbox)
const { resolveLimit } = sandbox

const failures = []
function check(name, cond) {
  console.log(`${cond ? 'ok  ' : 'FAIL'} ${name}`)
  if (!cond) failures.push(name)
}

// The default is ONE issue -- absent, junk, and non-positive-but-not-zero all fall here.
check('absent limit -> 1 (the default bounded run)', resolveLimit({}) === 1)
check('null args -> 1 (no throw)', resolveLimit(null) === 1)
check('limit:1 -> 1', resolveLimit({ limit: 1 }) === 1)
check('limit:3 -> 3 (caps at exactly N)', resolveLimit({ limit: 3 }) === 3)
check('string number limit:"5" -> 5', resolveLimit({ limit: '5' }) === 5)
check('non-numeric limit -> 1 (junk falls to the default)', resolveLimit({ limit: 'x' }) === 1)
check('negative limit -> 1 (nonsense falls to the default)', resolveLimit({ limit: -2 }) === 1)

// Draining is the explicit opt-in: noLimit:true or limit:0.
check('limit:0 -> Infinity (drain -- back-compat with the old signal)',
  resolveLimit({ limit: 0 }) === Infinity)
check('limit:"0" -> Infinity (drain -- string form)', resolveLimit({ limit: '0' }) === Infinity)
check('noLimit:true -> Infinity (drain)', resolveLimit({ noLimit: true }) === Infinity)
// An explicit Infinity must NOT collapse to 1 (parseInt(Infinity) is NaN).
check('limit:Infinity -> Infinity (explicit unlimited)', resolveLimit({ limit: Infinity }) === Infinity)
check('limit:"Infinity" -> Infinity (explicit unlimited, string form)',
  resolveLimit({ limit: 'Infinity' }) === Infinity)
check('noLimit:true wins over a positive limit -> Infinity',
  resolveLimit({ noLimit: true, limit: 2 }) === Infinity)
check('noLimit:false with a positive limit -> that limit',
  resolveLimit({ noLimit: false, limit: 2 }) === 2)
check('noLimit falsy (undefined) + absent limit -> 1',
  resolveLimit({ noLimit: undefined }) === 1)

console.log()
if (failures.length) {
  console.log(`FAILURES: ${failures.join(', ')}`)
  process.exit(1)
}
console.log('drain limit resolves as expected')
process.exit(0)
