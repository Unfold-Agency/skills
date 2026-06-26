# Reconciliation (Sync mode)

How to bring an existing set of GitHub issues back in line with a changed TDD. The prime directive: **the TDD is canonical; the issue is a projection.** You never edit a requirement in an issue to change scope -- you change the TDD and re-sync. And you **never overwrite a human's notes**. Reconciliation reasons about exactly one kind of drift -- TDD capability vs. its issue -- because the version-lock gate guarantees the TDD already matches the PRD. Generate mode is this engine run against an empty existing set.

## 1. Build the two maps

Pull the managed issues once (the preflight already cached this query):

```
gh issue list --repo <owner/name> --label make-issues --state all --limit 1000 \
  --json number,title,state,stateReason,labels,body,assignees,closedByPullRequestsReferences,milestone,updatedAt,url
```

- **`by_cap[cap_id] -> issue`.** The match key is the meta block's `trace_tdd` (parse the YAML between `<!-- make-issues:meta -->` and `<!-- /make-issues:meta -->` in `body`). If the meta block is missing or malformed, **do not try to auto-recover by parsing the body** -- the `## Traceability` table is free prose, not a machine contract. Flag the issue and stop reconciling it; a human reads the capability ID from that table, re-stamps the meta block, and re-runs the sync. One capability may map to more than one issue (it was sliced into several) -- keep them all.
- **`tdd_caps[cap_id] -> {record, fingerprint}`.** From `item_fingerprint.py docs/tdd-data.yaml` plus the records themselves. Skip `superseded`/`deferred` capabilities when deciding what should exist, but keep their IDs so you can recognize an issue that points at one (an orphan, below).
- **`cap_to_phase` + `phase_title`** (only when the TDD has a plan). From `phase_milestones.py docs/tdd-data.yaml --json`. Used by the milestone-alignment pass (§6), independently of the fingerprint axis.

## 2. Detect each issue's state

From the JSON fields above:

| State | Condition |
|---|---|
| **completed** | `state == CLOSED` and `stateReason == COMPLETED` |
| **won't-do** | `state == CLOSED` and `stateReason == NOT_PLANNED` |
| **started** | `state == OPEN` and (`assignees` non-empty **or** `closedByPullRequestsReferences` non-empty **or** an in-progress convention label such as `status:doing`) |
| **not-started** | `state == OPEN` and none of the started signals |

"Started" is **inferred**, not authoritative -- GitHub has no native in-progress state, and a hand-started branch with no closing PR will read as not-started (see SKILL.md, *Honest limits*). When unsure, treat as started: the cost of a needless flag is lower than the cost of editing under someone's feet.

## 3. The decision tree

For each capability, compare its current fingerprint to the one stamped in the matching issue's meta block, then branch on the issue's state:

```
no matching issue          -> CREATE   (new capability, or Generate mode)
fingerprint == stamped     -> SKIP     (no-op; cosmetic edits already hashed out)
fingerprint != stamped:
    not-started            -> AUTO-UPDATE managed regions; append changelog; re-stamp
    started + autonomy afk  -> AUTO-UPDATE + COMMENT-AND-FLAG; add label needs-rebase
    started + autonomy hitl -> COMMENT-AND-FLAG only (no body edit); add label spec-drift
    completed              -> FOLLOW-UP issue (new; traces to <cap>; "supersedes #<closed>")
                              -- a follow-up that backs out shipped work is HITL
    won't-do               -> SKIP, note in report (respect the human decision)
```

And for issues whose capability has vanished from the TDD (orphans -- `cap_id` no longer in `tdd_caps`, or it is now `superseded`/`deferred`):

```
orphan + not-started       -> CLOSE with stateReason NOT_PLANNED; changelog note
                              ("capability superseded in TDD v<X>")
orphan + started/completed -> COMMENT-AND-FLAG; add label orphaned
                              (never close shipped or in-flight work)
```

Each action is **keyed on fingerprint equality**, so the whole sync is idempotent: a re-run with no TDD change skips everything and creates no duplicates.

## 4. Auto-update without touching the human region

An AUTO-UPDATE rewrites only the managed regions: the prose above the meta marker, the `make-issues:meta` block, and the `make-issues:changelog` block. The `make-issues:human` block is preserved **byte-for-byte**. Do it as marker-anchored string surgery, not a regenerate:

1. Read the current `body` from the cached JSON.
2. Match the three regions non-greedily on their exact markers:
   - meta: `<!-- make-issues:meta -->` ... `<!-- /make-issues:meta -->`
   - changelog: `<!-- make-issues:changelog -->` ... `<!-- /make-issues:changelog -->`
   - human: `<!-- make-issues:human -->` ... `<!-- /make-issues:human -->`
3. Capture the human block verbatim. It is never a replacement target.
4. Substitute the new meta (re-stamped `fingerprint` + `source_versions`) and the new changelog (append a dated entry on top; never rewrite old entries). Recompute the summary prose region from the updated capability -- including the `## Traceability` table, whose IDs/titles and "Born from" versions must match the re-stamped meta.
5. **Defensive asserts before writing:** exactly one match for each managed marker pair; the captured human block appears unchanged in the new body (`human_before in body_after`); no nested or duplicated markers. If any assert fails, a human edited the markers -- **abort the edit and COMMENT-AND-FLAG instead.**
6. Apply via stdin so nothing touches disk:
   ```
   printf '%s' "$NEW_BODY" | gh issue edit <N> --repo <owner/name> --body-file -
   ```
   The version bump rides along in the re-stamped `source_versions` and the
   Traceability table's "Born from" line -- there is no separate label to swap.

## 5. Dependencies are write-only

GitHub dependency edges (`--blocked-by`/`--blocking`) **cannot be read back** through `gh issue ... --json` at any version. So reconciliation does not diff live edges. Instead it works from the **desired DAG derived from the current TDD**: cycle-check that graph (white/grey/black DFS; report any `A -> B -> A` path and emit no edges for that component), then re-assert the edges with native flags. Re-asserting an edge that already exists is a harmless no-op, which keeps the operation idempotent. Reading edges back, or detecting a human-removed edge, would require GraphQL and is out of scope.

## 6. Phase milestones are re-asserted every sync

When the TDD has an implementation plan, each issue belongs to a GitHub milestone -- one per phase, title `Phase <N>: <name>`. This is a **separate axis from the fingerprint decision tree** (§3), and it runs on every sync regardless of fingerprint, exactly like the dependency-edge re-assertion in §5. Phase is sequencing, not contract -- it lives only in the TDD's `implementation_phases`, never on a capability record, so a re-phase never changes a per-capability fingerprint and never trips `needs-rebase`/`spec-drift`.

1. **Ensure the milestones exist:** `phase_milestones.py docs/tdd-data.yaml --ensure --repo <owner/name>`. Idempotent; it creates missing milestones and patches a renamed/relabelled one in place (matched on the leading `Phase <N>`), so re-sequencing never orphans a milestone its issues still hang off.
2. **For each managed issue**, compute its intended phase from `cap_to_phase` and its `trace_tdd` (the **latest** phase among its capabilities; a phase-spanning issue is filed under the latest and noted as a slicing smell). Compare to the issue's live `milestone` (from the JSON above).
3. **If they differ, re-assign silently** -- `gh issue edit <N> --repo <owner/name> --milestone "Phase <N>: <name>"` -- and record it in the report. Do **not** add a flag: a moved capability is a re-sequence, not a scope change, whatever the issue's state (not-started, started, or HITL). An issue with no traced capability in the plan keeps whatever milestone it has and is reported.
4. A TDD with **no plan** skips this pass entirely; existing milestones are left untouched.

## 7. The report (every run)

Print the receipt -- it is the only durable record of what changed, and the coverage check that stands in for a validator:

- **Coverage:** every `active` capability has >=1 issue, or the gap is listed.
- **Traceability:** every managed issue resolves to a current capability, with PRD trace and both versions stamped.
- **DAG integrity:** the desired dependency graph is acyclic (or the cycle is named).
- **Lock:** the version-lock gate passed (asserted in preflight).
- **Drift:** every changed-fingerprint capability is accounted for by one of the actions above -- created, updated, flagged, closed, or followed-up.
- **Phases** (when the TDD has a plan): every active phase has >=1 issue and every issue has a milestone, or the gap is named; plus any phase-spanning issue filed under its latest phase.

Summarize counts: created, updated, flagged, closed, follow-ups, skipped; and, with a plan, milestones created/updated and issues re-assigned to a new phase.
