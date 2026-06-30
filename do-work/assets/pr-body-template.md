<!--
  PR BODY TEMPLATE -- do-work
  The pull request that ships one issue's slice. It carries the same trace the
  issue does, so the thread (requirement -> ADR -> issue -> PR) stays intact.

  Fill the angle-bracket placeholders, strip these authoring comments, then open
  the PR. Title follows do-git-workflow: "<emoji> <type>(scope): <summary>".
  One issue = one slice = one PR.
-->

## Summary

<!-- What this PR builds, in plain words. The slice from the issue's "What to
     build", as actually implemented. One short paragraph. -->

Closes #<N>

<!-- `Closes #<N>` is required: merging closes the issue as COMPLETED and links
     the PR back to it. Add more `Closes #` lines only if one PR genuinely ships
     more than one issue (it usually should not). -->

## Acceptance criteria

<!-- Mirror the issue's acceptance criteria; tick what this PR satisfies. The
     last box is the build gate and must be checked before review/merge. -->
- [ ] <criterion 1>
- [ ] <criterion 2>
- [ ] Typecheck / lint / tests pass

## How it was verified

<!-- The build gate run (the commands and their result) plus the issue's test
     plan: unit / integration / e2e / a11y / perf as applicable. Enough that a
     reviewer can re-run it. -->

## Traceability

<!-- Copied from the issue's make-issues:meta block, so the PR carries the trace.
     Do not invent IDs here; mirror what the issue stamps. -->
- Requirement: `<trace_req, e.g. FR-CHK-001>` (feature: `<slug>`)
- Governing decision: `<trace_adr, e.g. ADR-0001>`
- Source version: `<feature_version this was born from>`
- Autonomy: `<afk | hitl>`  <!-- hitl PRs are never auto-merged; a human reviews and merges -->

## Assumptions & mocks

<!-- DANGEROUS MODE ONLY (omit this section otherwise). When built under
     --dangerously, list every best-practice default chosen for an ambiguous spec
     and every mock/placeholder created for a missing external (each tagged
     FIXME(dangerously) in the code), with the needs-human-review follow-up issue
     opened for it. This is the reviewer's debt list -- what shipped on an
     assumption and must be confirmed. -->
- <what was assumed/mocked, where in the code> -- follow-up: #<M>

## Notes

<!-- Anything a reviewer needs: a caveat, a follow-up issue to file, a deliberate
     deferral, or why this is paused for a human (HITL). "None" if there is none. -->

🤖 Generated with [Claude Code](https://claude.com/claude-code)
