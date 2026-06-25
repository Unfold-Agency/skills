# Escalation & Hand-back

When a build cannot be done as the issue is written, the answer is never to edit the issue, the TDD, or the PRD to make it pass. The prime directive: **do-work raises the problem and stops; the right upstream lane fixes it.** The pipeline is forward-only -- upstream amends, re-locks, and re-syncs; then the work comes back here. Routing the problem to the wrong lane (or quietly coding around it) is how a clean trace rots.

**Who does what.** The worker building the issue is the one that hits the wall, so the *worker* raises the escalation -- it comments the reason, adds the `escalated` label, opens no PR, and returns `status: escalated`. That label is also the mechanism that takes the issue out of the queue: `select_work.py` excludes anything flagged `escalated`, so the orchestrator never re-dispatches it and the drain simply moves on to other work. The *orchestrator's* part is to record it in the run report and tell the user which lane to run next; it does not retry.

## The triage question

Before escalating, be sure it is an escalation and not just hard work. Ask: *can this slice be built to its acceptance criteria from the issue, the TDD capability it traces, and the PRD trace -- as they stand?*

- **Yes, it is just hard** -> build it. Difficulty is not a blocker.
- **No, and the gap is in the HOW** -> route to `/make-tdd` (design gap).
- **No, and the gap is in the WHAT** -> route to `/make-prd` (requirement problem).
- **The issue is already marked stale** -> route to `/make-issues` (it syncs first).

Pin the problem to IDs before routing. A blocker you cannot tie to a `trace_tdd` capability or a `trace_prd` requirement is not understood well enough to escalate yet -- read more first.

## Route 1 -- design gap or contradiction -> `/make-tdd`

The requirement is clear, but the design does not support it: an integration contract the TDD never specified, a state the state machine omits, two capabilities that contradict, a binding constraint that makes the described approach impossible. This is a **build-blocker**, one of make-tdd's amend triggers.

Hand back with what the TDD amend needs:

- The **`trace_tdd` capability ID(s)** involved, and what is missing or contradictory -- concretely, at the seam where the build stalled.
- What you expected the design to say, and why the current design cannot be built to the acceptance criteria.
- Anything you learned from the attempt that the design should absorb (a real rate limit, an auth model that does not work as assumed).

Then: comment this on the issue, add the `escalated` label, and stop building it. Tell the user the next step is `/make-tdd` (amend, which re-derives and re-locks), then `/make-issues` (sync, which updates or flags this issue), and then `/do-work` again.

## Route 2 -- a wrong or unsatisfiable requirement -> `/make-prd` (`ESC-`)

The acceptance criterion itself is wrong: it cannot be satisfied as written, it contradicts another requirement, or building it would contradict the PRD's own objective. This is a PRD **escalation** -- an agent that cannot satisfy an acceptance criterion as written is exactly what the `ESC-` record exists for.

You **propose**; you never decide. Prepare an `ESC-` record per make-prd's schema:

- **Required:** `affected_ids` (the PRD requirement IDs at issue, found via the issue's `trace_prd`), `description` (what cannot be satisfied and why), `raised_by` (do-work, on behalf of the build).
- **Optional suggestions:** `proposed_resolution` and `proposed_change_class` -- offer them if you have a view, clearly marked as suggestions.
- **Not yours to set:** `decision` and `decision_rationale`. A named human validator sets those. do-work must never decide the change class or resolve the escalation.

Then: comment the escalation on the issue, add the `escalated` label, stop, and tell the user to run `/make-prd` to process the `ESC-` record. A PRD change reaches this issue only the long way around -- `/make-prd` -> `/make-tdd` (re-lock) -> `/make-issues` (sync) -> `/do-work`.

## Route 3 -- the issue is already stale -> `/make-issues`

If the issue carries `needs-rebase`, `spec-drift`, or `orphaned`, `make-issues` has already detected that the TDD moved under it. Fixing that is `make-issues`' job, not yours. `select_work.py` excludes these from the actionable queue for this reason. Do not build them. Tell the user to run `/make-issues` to reconcile; once the flag clears, the issue becomes buildable again.

## HITL stop points (not a failure, a gate)

An HITL issue is not blocked -- it is gated on a human, by design (a visual or brand judgment, a security or data-migration sign-off, anything touching production data or money, or backing out shipped work). Unlike an escalation, the spec is fine; a person simply must be in the loop. Handle it by stopping at the gate:

- If the human decision must come **before** the build, do not start -- surface the decision needed and wait.
- If a human must **review or sign off** before merge, build it, open the PR, and leave it for the human (do not auto-merge, ever).

HITL items never escalate upstream and are never drained or auto-merged; they wait for a person. Note each one in the run report so it is not silently skipped.

## Dangerous mode (`--dangerously`)

Under `--dangerously` (SKILL.md, *Dangerous mode*) the rules above are deliberately overridden for maximum throughput: the worker does **not** escalate-and-stop and HITL is **not** a stop point. Instead of raising a problem and waiting, the worker **resolves and proceeds**:

- **A design gap or an ambiguous/unsatisfiable criterion** -> pick the best-practice resolution, build it, and open a `needs-human-review` follow-up issue describing the decision. Do not add the `escalated` label; do not stop the run.
- **A missing external** (an API, seed data, a credential, an upstream service) -> create a clearly-marked mock/placeholder (a fixture, a stub, env defaults) tagged `FIXME(dangerously)` so the gate passes against the mock, then open a follow-up issue for it.
- **HITL** -> build it and merge it like any other issue.

The line that does **not** move: you still **never edit the PRD, the TDD, or an issue's managed scope**. Dangerous mode resolves *implementation* ambiguity and mocks *missing externals* -- it does not rewrite requirements. And it still respects the make-issues drift gates: an issue flagged `needs-rebase` / `spec-drift` / `orphaned` / `escalated` is **skipped**, because the spec itself is known stale and only `/make-issues` can sync it. A follow-up issue is a `needs-human-review` triage marker, not a `make-issues` work item, so the loop never re-builds its own mocks. See SKILL.md for the merge policy (merge on green CI even with open findings; never merge a red CI).

## What hand-back never does

- It never edits the PRD, the TDD, or the scope inside an issue. Those are owned upstream.
- It never picks a change class or resolves an escalation -- it proposes; a human decides.
- It never closes an issue to get it out of the queue. Escalated work stays open, labelled, and commented, so the thread is intact when it comes back.
