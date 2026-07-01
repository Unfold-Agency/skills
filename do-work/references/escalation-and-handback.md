# Escalation & Hand-back

When a build cannot be done as the issue is written, the answer is never to edit the issue or the specs to make it pass. The prime directive: **do-work raises the problem and stops; the right upstream lane fixes it.** The pipeline is forward-only -- upstream amends and re-syncs; then the work comes back here. Routing the problem to the wrong lane (or quietly coding around it) is how a clean trace rots.

**Who does what.** The worker building the issue is the one that hits the wall, so the *worker* raises the escalation -- it comments the reason, adds the `escalated` label, opens no PR, and returns `status: escalated`. That label is also the mechanism that takes the issue out of the queue: `select_work.py` excludes anything flagged `escalated`, so the orchestrator never re-dispatches it and the drain simply moves on to other work. The *orchestrator's* part is to record it in the run report and tell the user which lane to run next; it does not retry.

## The triage question

Before escalating, be sure it is an escalation and not just hard work. Ask: *can this slice be built to its acceptance criteria from the issue (which embeds the requirement, its EARS criteria, and a governing-ADR snippet) and the governing ADR it traces -- as they stand?*

- **Yes, it is just hard** -> build it. Difficulty is not a blocker.
- **No, and the gap is in the HOW** -> route to `/make-arch` (a design decision is missing or wrong).
- **No, and the gap is in the WHAT** -> route to `/make-spec` (the requirement itself is wrong).
- **The issue is already marked stale, or has no acceptance criteria to build against** -> route to `/make-issues` (it reconciles or re-authors first).

Pin the problem to IDs before routing. A blocker you cannot tie to the issue's `trace_req` requirement or its `trace_adr` decision is not understood well enough to escalate yet -- read more first.

## Route 1 -- design gap or contradiction -> `/make-arch`

The requirement is clear, but the architecture does not support it: an integration the ADRs never decided, a data shape the design omits, a governing ADR that contradicts the requirement, a decision that makes the described approach impossible. The fix is a new or superseding ADR.

Hand back with what `/make-arch` needs:

- The **`trace_adr` decision(s)** involved (or the gap where no ADR governs the requirement), and what is missing or contradictory -- concretely, at the seam where the build stalled.
- What you expected the architecture to decide, and why the current decision cannot be built to the acceptance criteria.
- Anything you learned from the attempt that the decision should absorb (a real rate limit, an auth model that does not work as assumed).

Then: comment this on the issue, add the `escalated` label, and stop building it. Tell the user the next step is `/make-arch` (add or supersede the ADR), then `/make-issues` (reconcile, which updates or flags this issue), and then `/do-work` again.

## Route 2 -- a wrong or unsatisfiable requirement -> `/make-spec`

The acceptance criterion itself is wrong: it cannot be satisfied as written, it contradicts another requirement, or building it would contradict an overview goal. This is a **spec defect** in the WHAT, and the fix is a `/make-spec` amend of the feature -- not something you resolve in code.

You **propose**; you never decide. Hand back with:

- The **`trace_req` requirement ID** at issue (and the feature slug from the issue's `feature`), and a plain statement of what cannot be satisfied and why.
- A suggested resolution if you have one, clearly marked as a suggestion.
- What you must **not** do: rewrite the requirement, pick the change yourself, or build a "best-practice" reinterpretation to get green. A human decides the amend; `/make-spec` records it (and the CHANGELOG delta).

Then: comment the problem on the issue, add the `escalated` label, stop, and tell the user to run `/make-spec` (amend the feature). The change reaches this issue the long way around -- `/make-spec` (amend) -> `/make-arch` if a decision is affected -> `/make-issues` (reconcile) -> `/do-work`. **This is the spec defect that even `--dangerously` escalates rather than papering over** (see below).

## Route 3 -- the issue is already stale -> `/make-issues`

If the issue carries `needs-rebase`, `spec-drift`, `orphaned`, or `stale-against-dependency`, `make-issues` has already detected that the spec moved under it (or a dependency did). Fixing that is `make-issues`' job, not yours. `select_work.py` excludes these from the actionable queue for this reason. Do not build them. Tell the user to run `/make-issues` to reconcile; once the flag clears, the issue becomes buildable again.

The same lane owns an issue with **no acceptance criteria to build against** -- a `make-issues` `amendment` authored without criteria (a spec issue always embeds its EARS criteria, so this is an amendment case). `select_work.py` treats a criteria-less issue as hitl and keeps it out of the afk drain, because an unattended worker has nothing to verify "done" against; do **not** invent criteria to make it buildable. Route it to `/make-issues` to author the acceptance criteria (or promote the amendment to a real requirement), then it becomes afk-buildable. Likewise, an `amendment` whose feature anchor was removed from the specs is flagged `orphaned` by `/make-issues` and handled exactly like any stale issue above -- a human re-anchors or closes it there, not here.

## HITL stop points (not a failure, a gate)

An HITL issue is not blocked -- it is gated on a human, by design (a visual or brand judgment, a security or data-migration sign-off, anything touching production data or money, or backing out shipped work). Unlike an escalation, the spec is fine; a person simply must be in the loop. Handle it by stopping at the gate:

- If the human decision must come **before** the build, do not start -- surface the decision needed and wait.
- If a human must **review or sign off** before merge, build it, open the PR, and leave it for the human (do not auto-merge, ever).

HITL items never escalate upstream and are never drained or auto-merged; they wait for a person. Note each one in the run report so it is not silently skipped.

## Dangerous mode (`--dangerously`)

Under `--dangerously` (SKILL.md, *Dangerous mode*) the rules above are deliberately overridden for maximum throughput: for *implementation* problems the worker does **not** escalate-and-stop, and HITL is **not** a stop point. Instead of raising the problem and waiting, the worker **resolves and proceeds** -- with one carve-out:

- **A design gap or an *implementation* ambiguity** (a wiring choice, a default the spec leaves open) -> pick the best-practice resolution, build it, and open a `needs-human-review` follow-up issue describing the decision. Do not add the `escalated` label; do not stop the run.
- **A missing external** (an API, seed data, a credential, an upstream service) -> create a clearly-marked mock/placeholder (a fixture, a stub, env defaults) tagged `FIXME(dangerously)` so the gate passes against the mock, then open a follow-up issue for it.
- **An *unsatisfiable* acceptance criterion** -- a contradiction in the WHAT, not an implementation choice -> this is a **spec defect** and it **still escalates and stops the issue** (Route 2), even here. `--dangerously` resolves implementation ambiguity; it does not invent a requirement to paper over a broken one.
- **HITL** -> build it and merge it like any other issue (named in the run's HITL auto-merge manifest).

The line that does **not** move: you still **never edit the specs or an issue's managed scope**. Dangerous mode resolves *implementation* ambiguity and mocks *missing externals* -- it does not rewrite requirements. And it still respects the make-issues drift gates: an issue flagged `needs-rebase` / `spec-drift` / `orphaned` / `stale-against-dependency` / `escalated` is **skipped**, because the spec itself is known stale and only `/make-issues` can reconcile it. A follow-up issue is a `needs-human-review` triage marker, not a `make-issues` work item, so the loop never re-builds its own mocks. See SKILL.md for the merge policy (merge on green CI even with open findings; never merge a red CI).

## What hand-back never does

- It never edits the specs (the overview, a feature, or an ADR) or the scope inside an issue. Those are owned upstream.
- It never decides the amend or resolves the spec defect -- it proposes; a human decides.
- It never closes an issue to get it out of the queue. Escalated work stays open, labelled, and commented, so the thread is intact when it comes back.
