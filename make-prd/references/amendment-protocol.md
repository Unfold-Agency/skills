# Amendment Protocol (Amend Mode)

How to change a PRD that already exists. The prime directive: **diff, don't rewrite**. Regenerating a PRD from scratch destroys the version history, the ID stability, and every downstream pin. Amend mode touches only what the change touches.

## 1. Intake

Read, in order:
1. The existing PRD Markdown (master + shards if sharded)
2. The existing `prd-data.yaml` (you'll need it for `--prev` validation)
3. The change trigger -- one of:
   - **ESC- escalation record** (an agent or human couldn't satisfy a criterion as written)
   - **UAT issue** (bug or change request from Lane 7)
   - **Client request** (new ask, scope change, decision)
   - **Discovery** (new fact that invalidates an assumption or constraint)

If the trigger doesn't name affected IDs, find them before classifying. A change you can't pin to IDs isn't understood well enough to classify yet.

## 2. Classification

Apply the test from Section 1.2 of the template, in this order:

**Does the change alter any ID'd item in the PRD?**
- **No** → Ticket refinement. The PRD does not change. Tell the user this explicitly, explain why (e.g., "final button copy is design detail; FR-012's behavior is unchanged"), and stop. Resisting unnecessary amendments is part of the job -- a PRD that bumps versions for trivia trains people to ignore versions.

**Yes → is the change additive/clarifying, or does it alter meaning?**
- **Additive or clarifying** (new FR within approved scope, a KU answered, a source added, wording tightened without changing what's required) → **Minor**. Bump x.Y.
- **Alters meaning** (an FR's behavior changes, scope items move in or out, an objective or constraint changes, anything is cut) → **Major**. Bump X.0. Requires recorded approval from Section 12 authorities before status can return to `approved`.

Borderline calls: classify conservatively (prefer major) and log the reasoning in Section 13. If the user disagrees, reclassifying down is cheap; discovering at UAT that a "minor" change rewrote scope is not.

## 3. Escalation handling

When the trigger is an escalation:

1. Ingest or create the ESC- record per `assets/prd-data-schema.yaml`. Required fields before anything else happens: `affected_ids`, `description`, `raised_by`.
2. The skill (or the raising agent) may fill `proposed_resolution` and `proposed_change_class`. These are suggestions.
3. **Stop and require a human decision.** A named `validator` must set `decision` and `decision_rationale`. If the user is that human, ask them directly: present the escalation, the affected requirement text, and the proposed options. Never proceed on the proposal alone.
4. Execute the decision:
   - `refine-ticket` → no PRD change; record the decision on the ESC record; the ticket resumes.
   - `rejected` → no PRD change; the criterion stands; pass the rationale back as guidance.
   - `minor-amendment` / `major-amendment` → proceed to step 4 below; the change_log entry's `triggered_by` references the ESC id.

## 4. Applying the diff

- Edit only the affected sections of the Markdown.
- **Never delete or renumber an ID.** Items leave service via `status: superseded` (replaced or cut) or `status: deferred` (pushed to a later phase). A superseded FR's replacement gets a NEW id with a note pointing back.
- Add a Version History row (Section 1.1): version, class, changed IDs, summary, trigger reference.
- Update frontmatter: `version`, `supersedes`, `last_updated`. Major amendments set `status: in-review` until approvals land.
- Log judgment calls in Section 13.

## 5. Re-derive and validate

Regenerate `prd-data.yaml` from the amended Markdown (master + shards). Then:

```
python scripts/validate_prd.py prd-data.yaml --prd-md PRD.md --prev <prior prd-data.yaml>
```

`--prev` is not optional in amend mode -- it enforces V-005 (no ID present in the prior version may vanish).

## 6. Propagation report (major amendments)

The skill prepares propagation; humans execute it. Output a report containing:

- **Changed IDs** and old → new meaning, one line each
- **Approval owed**: who must sign per Section 12, and that status is `in-review` until they do
- **TDD review**: which changed IDs plausibly touch the TDD (integrations, constraints, NFRs almost always do; copy-level FR tweaks may not)
- **Ticket impact**: tickets are pinned to the PRD version they were generated against, so the affected set = tickets referencing any changed ID. State the query, list known affected tickets if ticket data is available, and the disposition options (update / supersede / replace / new).
- **Remaining 1.3 steps** not yet executed, as a checklist the user can run down.

For minor amendments the report is lighter: changed/added IDs, whether new tickets are warranted, confirmation that existing tickets are untouched.