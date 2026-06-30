# Reconciliation (Sync mode)

How to bring an existing set of GitHub issues back in line with changed specs. The prime directive: **the specs are canonical; the issue is a projection.** You never edit a requirement in an issue to change scope -- you change the feature spec and re-sync. And you **never overwrite a human's notes**. Reconciliation reasons about exactly one kind of drift -- a feature **requirement** vs. its issue -- because the fail-closed fingerprint gate (preflight) guarantees the specs are internally consistent before you start. Generate mode is this engine run against an empty existing set.

The reconcile is **bounded by construction**: `scripts/analyze.py` walks the finite set of requirements and compares each one's live fingerprint against its issue's stamped one -- an **exhaustive** scan, never CHANGELOG-scoped, so a stale or missing CHANGELOG entry can never hide a real change. Every op carries a stable idempotency key, and the refactor fan-out is capped. The committed watermark records "since the last sync" for the report (the executor advances it after a successful sync); the CHANGELOG is the human narrative of the delta, not an input to the scan. `scripts/analyze.py` computes the whole plan read-only and is the **hard gate** -- no GitHub write happens until it exits 0 or a human approves its remediation report.

## 1. Pull the issues and run analyze

Pull the managed issues once:

```
gh issue list --repo <owner/name> --label make-issues --state all --limit 1000 \
  --json number,title,state,stateReason,labels,body,assignees,closedByPullRequestsReferences,milestone,updatedAt,url \
  > issues.json
```

Then run the planner -- this is the gate:

```
python scripts/analyze.py --spec-dir docs/specs --issues issues.json --max-refactors 10
```

It exits **0** when the plan is clean and safe to execute, or **1** on **blocking drift** (a malformed meta block, or a refactor fan-out over the cap). On exit 1, **do not write anything**: present its remediation report and get a human to resolve or approve it first. The plan is also available as JSON (`--json`) for the review pass.

Internally analyze builds the match map: **`by_req[req_id] -> [issue, ...]`**, matching on the meta block's `trace_req` (the YAML between `<!-- make-issues:meta -->` and `<!-- /make-issues:meta -->` in `body`). If the meta block is missing or malformed, it does **not** try to auto-recover from the prose body -- the `## Traceability` table is free prose, not a machine contract. It records the issue as **blocking drift**; a human reads the requirement id from that table, re-stamps the meta block, and re-runs. One requirement may map to more than one issue (it was sliced into several) -- all are kept. The per-requirement fingerprint comes from `item_fingerprint.py docs/specs`; the ADR statuses (for the refactor trigger) from `arch-data.yaml`.

## 2. The watermark and the CHANGELOG delta

`docs/specs/.make-issues-sync.json` is a committed, per-feature watermark -- the marker that makes "since the last sync" a fact, not a vibe:

```json
{
  "checkout": { "feature_version": "1.2", "last_changelog_entry": "2026-06-20 -- v1.2" },
  "cart":     { "feature_version": "1.0", "last_changelog_entry": "2026-06-01 -- v1.0" }
}
```

`analyze.py` is **exhaustive**: every run it walks every requirement and compares its live fingerprint against the matching issue's stamped one. It does **not** read the CHANGELOG, and the watermark does **not** scope the plan -- a full fingerprint scan is the safe choice, because a stale or missing CHANGELOG entry can never hide a real change. The CHANGELOG's structured **Added / Modified / Removed** id lists are the human narrative of the delta (and what you write into the report), not an input that narrows the scan. The watermark records the last sync point per feature; after a successful run, **advance the watermark** to each feature's current `feature_version` and the latest CHANGELOG entry, and commit it. The finite requirement set and the refactor fan-out cap are the real bounds.

`analyze.py` reads the watermark and surfaces it in the plan; it does not write it -- advancing the watermark is the executor's final step, after the GitHub writes succeed.

## 3. Detect each issue's state

From the JSON fields above (analyze does this in `issue_state` / `is_merged`):

| State | Condition |
|---|---|
| **completed** | `state == CLOSED` and `stateReason == COMPLETED` |
| **won't-do** | `state == CLOSED` and `stateReason == NOT_PLANNED` |
| **started** | `state == OPEN` and (`assignees` non-empty **or** `closedByPullRequestsReferences` non-empty **or** an in-progress convention label such as `status:doing`) |
| **not-started** | `state == OPEN` and none of the started signals |
| **merged** | completed, **or** open with a `MERGED` closing PR (shipped work -- the refactor trigger) |

"Started" is **inferred**, not authoritative -- GitHub has no native in-progress state, and a hand-started branch with no closing PR will read as not-started (see SKILL.md, *Honest limits*). When unsure, treat as started: the cost of a needless flag is lower than the cost of editing under someone's feet.

## 4. The decision tree

For each requirement, compare its current fingerprint to the one stamped in the matching issue's meta block, then branch on the issue's state:

```
no matching issue           -> CREATE   (new requirement, or Generate mode)
fingerprint == stamped       -> SKIP     (no-op; advisory/cosmetic edits hashed out)
fingerprint != stamped:
    not-started             -> UPDATE managed regions; append changelog; re-stamp
    started + autonomy afk   -> COMMENT-AND-FLAG; add label needs-rebase
    started + autonomy hitl  -> COMMENT-AND-FLAG; add label spec-drift
    completed / merged       -> REFACTOR (new HITL issue; backs out/reworks shipped work)
    won't-do                -> SKIP, note in report (respect the human decision)
```

For a requirement whose `status` is now `superseded`/`deferred`, or that has vanished from the specs entirely (an **orphan** -- its `req_id` is gone from the spec set):

```
orphan + not-started/started -> STALE/CLOSE with stateReason NOT_PLANNED; changelog note
                                ("requirement superseded/removed in feature v<X>")
orphan + merged              -> REFACTOR; add label orphaned + refactor
                                (never silently close shipped work -- rework it deliberately)
```

And the new **ADR-driven** trigger, independent of the requirement text:

```
governing ADR superseded/deprecated AND the issue is merged -> REFACTOR
    (the decision behind shipped work flipped, even if the requirement text didn't)
```

**REFACTOR** is the new action the merged/shipped state needs: a MODIFIED or REMOVED requirement whose issue is completed/merged, or a requirement whose governing ADR was superseded and whose issue merged, opens a **refactor issue** -- always HITL, labelled `refactor`, traced back to the requirement and the superseding ADR, and linked to the issue it reworks. It is never an auto-edit and never a silent close: shipped code only changes under a human's eye.

Each action is **keyed on fingerprint equality** and carries a **stable idempotency key** (`action:req:fingerprint[:issue]`), so the whole sync is idempotent: a re-run with no spec change skips everything, creates no duplicates, and reproduces the same keys.

## 5. The refactor fan-out cap

A single foundational change (a reversed ADR, a removed shared requirement) could fan out into dozens of refactors of already-shipped work. analyze caps this with `--max-refactors N` (default 10):

- Plan up to N refactor issues.
- If more would open, plan **only N**, plan **one** `refactor-tracking` issue recording the deferred count ("M more refactors pending"), and **block the gate** (exit 1) so a human triages the cascade before it runs.
- The truncation is reported explicitly -- the overflow is never silently dropped.

## 6. Auto-update without touching the human region

An UPDATE rewrites only the managed regions: the prose above the meta marker, the `make-issues:meta` block, and the `make-issues:changelog` block. The `make-issues:human` block is preserved **byte-for-byte**. Do it as marker-anchored string surgery, not a regenerate:

1. Read the current `body` from the cached JSON.
2. Match the three regions non-greedily on their exact markers:
   - meta: `<!-- make-issues:meta -->` ... `<!-- /make-issues:meta -->`
   - changelog: `<!-- make-issues:changelog -->` ... `<!-- /make-issues:changelog -->`
   - human: `<!-- make-issues:human -->` ... `<!-- /make-issues:human -->`
3. Capture the human block verbatim. It is never a replacement target.
4. Substitute the new meta (re-stamped `fingerprint` + `source_version`) and the new changelog (append a dated entry on top; never rewrite old entries). Recompute the summary prose -- the embedded requirement text, the EARS acceptance criteria, the interface, the governing-ADR snippets, and the `## Traceability` table -- from the updated requirement, so the embedded slice and the "Born from" version match the re-stamped meta.
5. **Defensive asserts before writing:** exactly one match for each managed marker pair; the captured human block appears unchanged in the new body (`human_before in body_after`); no nested or duplicated markers. If any assert fails, a human edited the markers -- **abort the edit and COMMENT-AND-FLAG instead.**
6. Apply via stdin so nothing touches disk:
   ```
   printf '%s' "$NEW_BODY" | gh issue edit <N> --repo <owner/name> --body-file -
   ```
   The version bump rides along in the re-stamped `source_version` and the Traceability table's "Born from" line -- there is no separate label to swap.

## 7. Dependencies are write-only; the body mirror is what we verify

GitHub dependency edges (`--blocked-by`/`--blocking`) **cannot be read back** through `gh issue ... --json` at any version. So reconciliation does not diff live native edges. Instead it works from the **desired DAG derived from the requirements' `depends_on`** (requirement ids, which may cross features): cycle-check that graph (white/grey/black DFS; report any `A -> B -> A` path and emit no edges for that component), then re-assert the edges with native flags (a re-assert is a harmless idempotent no-op). The verifiable guarantee is the **issue-body `## Dependencies` mirror**: read it back, resolve it to the desired DAG, and assert acyclicity. Reading native edges back, or detecting a human-removed one, would require GraphQL and is out of scope.

## 8. Phase milestones are re-asserted every sync (when there is a plan)

Phasing is **optional** in the new overview. When `overview-data.yaml` carries a `phasing` list, each issue belongs to a GitHub milestone -- one per phase, title `Phase <N>: <name>`. This is a **separate axis from the fingerprint decision tree** (§4), and it runs on every sync regardless of fingerprint, exactly like the dependency-edge re-assertion in §7. Phase is sequencing, not contract -- it lives only in the overview's `phasing`, keyed by feature slug, never on a requirement, so a re-phase never changes a per-requirement fingerprint and never trips `needs-rebase`/`spec-drift`.

1. **Ensure the milestones exist:** `phase_milestones.py docs/specs/overview-data.yaml --ensure --repo <owner/name>`. Idempotent; it creates missing milestones and patches a renamed/relabelled one in place (matched on the leading `Phase <N>`), so re-sequencing never orphans a milestone its issues still hang off.
2. **For each managed issue**, compute its intended phase from `feature_to_phase` and its meta `feature` slug. Compare to the issue's live `milestone` (from the JSON above).
3. **If they differ, re-assign silently** -- `gh issue edit <N> --repo <owner/name> --milestone "Phase <N>: <name>"` -- and record it in the report. Do **not** add a flag: a moved feature is a re-sequence, not a scope change. An issue whose feature is not in the plan keeps whatever milestone it has and is reported.
4. An overview with **no `phasing` plan** skips this pass entirely; existing milestones are left untouched.

## 9. The report (every run)

Print the receipt -- it is the only durable record of what changed, and the coverage check that stands in for a validator:

- **Coverage:** every `active` requirement has >=1 issue, or the gap is listed.
- **Traceability:** every managed issue resolves to a current requirement, with ADR trace (`trace_adr`) and the source `feature_version` stamped.
- **DAG integrity:** the desired dependency graph (from `depends_on`, mirrored in the issue body) is acyclic (or the cycle is named).
- **Integrity:** the fail-closed fingerprint gate passed (asserted in preflight).
- **Drift:** every changed-fingerprint requirement is accounted for by one of the actions above -- created, updated, flagged, refactored, closed, or followed-up (from the exhaustive per-requirement fingerprint scan).
- **Phases** (when the overview has a plan): every active phase has >=1 issue and every issue has a milestone, or the gap is named; plus any phase-spanning feature filed under its latest phase.
- **Watermark:** each feature's last-synced version (read for the report), and the new watermark the executor writes after the run.

Summarize counts: created, updated, flagged, closed, refactors, refactor-tracking, skipped; and, with a plan, milestones created/updated and issues re-assigned to a new phase. Report any refactor fan-out truncation explicitly.
