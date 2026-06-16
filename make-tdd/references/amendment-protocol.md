# Amendment Protocol (Amend Mode)

How to change a TDD that already exists. The prime directive: **diff, don't rewrite**. Regenerating a TDD from scratch destroys the version history, the ID stability, and every downstream issue pinned to a TDD version. Amend mode touches only what the change touches.

## 1. Run the location guard first

Before editing anything, reconcile where you are running against what the document claims as its `system_of_record`. The full matrix, the drift check, and the SUPERSEDED banner are in SKILL.md (*Location & system of record*) -- it applies to both modes, and amend mode is where drift actually bites. Two outcomes block the normal flow:

- **Canonical copy is the repo, and you are not in it** -- stop. Editing here forks the document. Direct the user to amend via `/make-tdd` in Claude Code, against `meta.repo.path`. Do not silently edit.
- **A `fingerprint` is recorded and the current content's recompute differs without a matching version bump** -- flag a possible out-of-band edit and ask the human to reconcile before proceeding. Someone changed the file outside the protocol.

If this run is a promotion event (a `claude-project` TDD now opened inside a repo), handle the promotion -- flip to `git`, set `repo` and `promoted_at`, regenerate the fingerprint, stamp the old Project copy SUPERSEDED -- before applying the substantive change.

## 2. Intake

Read, in order:
1. The existing TDD Markdown.
2. The existing `tdd-data.yaml` (you need it for `--prev` validation).
3. The change trigger -- one of:
   - **PRD amendment** (the WHAT changed; the most common trigger -- a new PRD version changed or added a requirement)
   - **Build blocker** (an engineer or agent hit something the design didn't anticipate)
   - **Vendor / platform change** (an API deprecation, a new limit, a license change)
   - **Discovery** (a new fact that invalidates an assumption or a decision)

If the trigger doesn't name affected IDs, find them before classifying. A change you can't pin to IDs isn't understood well enough to classify yet. When the trigger is a PRD amendment, start from its changed PRD IDs and trace forward: which capabilities, decisions, and contracts `satisfy` or `derive_from` them.

**The version lock is itself a trigger.** If the live PRD version is newer than the TDD's locked `prd_version`, the TDD is stale by definition -- that gap is an amend trigger. Re-derive against the new PRD and re-lock `meta.prd_version` to it. This lock is what lets the downstream `make-issues` reason about a single drift axis (TDD item vs. issue) and never PRD vs. issue: it refuses to run while the TDD's `prd_version` lags the live PRD.

## 3. Classification

Apply the test from Section 1.2 of the template, in order:

**Does the change alter any ID'd item in the TDD?**
- **No** → Refinement. The TDD does not change. Tell the user explicitly, explain why (e.g., "the retry interval is an implementation detail; INTG-002's contract is unchanged"), and stop. Resisting unnecessary amendments is part of the job.

**Yes → is the change additive/clarifying, or does it alter meaning?**
- **Additive or clarifying** (a new entity within the modeled system, an open question answered, a diagram added, wording tightened without changing a contract) → **Minor**. Bump x.Y.
- **Alters meaning** (a decision reverses, a data model changes shape, an API contract changes, a binding constraint changes, anything is cut) → **Major**. Bump X.0. Requires recorded architecture-review approval before status can return to `approved`.

Borderline calls: classify conservatively (prefer major) and log the reasoning. Reclassifying down later is cheap; discovering at build time that a "minor" change reshaped a contract is not.

## 4. Applying the diff

- Edit only the affected sections of the Markdown.
- **Never delete or renumber an ID.** Items leave service via `status: superseded` (replaced or cut) or `status: deferred` (pushed to a later phase). A superseded decision's replacement gets a NEW id with a note pointing back.
- Add a Version History row (Section 1.1): version, class, changed IDs, summary, trigger reference.
- Update frontmatter: `version`, `supersedes`, `last_updated`, and `prd_version` if the trigger was a PRD amendment. Major amendments set `status: review` until approval lands.

## 5. Re-derive and validate

Regenerate `tdd-data.yaml` from the amended Markdown, regenerate `meta.fingerprint`, then:

```
python scripts/validate_tdd.py tdd-data.yaml --prd prd-data.yaml --tdd-md TDD.md --prev <prior tdd-data.yaml>
```

`--prev` is not optional in amend mode -- it enforces V-009 (no ID present in the prior version may vanish). `--prd` should point at the PRD version this TDD now satisfies.

## 6. Propagation report

The skill prepares propagation; humans execute it. For **major** amendments, output:

- **Changed IDs** and old → new meaning, one line each.
- **Approval owed**: who must sign the architecture review, and that status is `review` until they do.
- **Coverage delta**: any PRD `must`/`should` requirement that is now unmapped because a capability was superseded -- the new gaps.
- **Issue impact**: issues (Lane 4 / `make-issues`) are pinned to the TDD version they were generated against, so the affected set = issues referencing any changed ID. State the query, list known affected issues if issue data is available, and the disposition options (update / supersede / replace / new).
- **Remaining steps** from Section 1.3 not yet executed, as a checklist.

For **minor** amendments the report is lighter: changed/added IDs, whether new issues are warranted, and confirmation that existing issues are untouched.
