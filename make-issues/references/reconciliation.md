# Reconciliation (Sync mode)

How to bring an existing set of GitHub issues back in line with a changed TDD. The prime directive: **the TDD is canonical; the issue is a projection.** You never edit a requirement in an issue to change scope -- you change the TDD and re-sync. And you **never overwrite a human's notes**. Reconciliation reasons about exactly one kind of drift -- TDD capability vs. its issue -- because the version-lock gate guarantees the TDD already matches the PRD. Generate mode is this engine run against an empty existing set.

## 1. Build the two maps

Pull the managed issues once (the preflight already cached this query):

```
gh issue list --repo <owner/name> --label make-issues --state all --limit 1000 \
  --json number,title,state,stateReason,labels,body,assignees,closedByPullRequestsReferences,updatedAt,url
```

- **`by_cap[cap_id] -> issue`.** The match key is the meta block's `trace_tdd` (parse the YAML between `<!-- make-issues:meta -->` and `<!-- /make-issues:meta -->` in `body`). If the meta block is missing or malformed, recover the capability ID from the body's `## Traceability` table (the human-readable mirror) and re-stamp the block before reconciling. One capability may map to more than one issue (it was sliced into several) -- keep them all.
- **`tdd_caps[cap_id] -> {record, fingerprint}`.** From `item_fingerprint.py <tdd-data.yaml>` plus the records themselves. Skip `superseded`/`deferred` capabilities when deciding what should exist, but keep their IDs so you can recognize an issue that points at one (an orphan, below).

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
4. Substitute the new meta (re-stamped `fingerprint` + `source_versions`) and the new changelog (append a dated entry on top; never rewrite old entries). Recompute the summary prose region from the updated capability.
5. **Defensive asserts before writing:** exactly one match for each managed marker pair; the captured human block appears unchanged in the new body (`human_before in body_after`); no nested or duplicated markers. If any assert fails, a human edited the markers -- **abort the edit and COMMENT-AND-FLAG instead.**
6. Apply via stdin so nothing touches disk:
   ```
   printf '%s' "$NEW_BODY" | gh issue edit <N> --repo <owner/name> --body-file -
   ```
7. Update stamps idempotently:
   ```
   gh issue edit <N> --repo <owner/name> \
     --add-label "src:tdd-<new>" --remove-label "src:tdd-<old>"
   ```

## 5. Dependencies are write-only

GitHub dependency edges (`--blocked-by`/`--blocking`) **cannot be read back** through `gh issue ... --json` at any version. So reconciliation does not diff live edges. Instead it works from the **desired DAG derived from the current TDD**: cycle-check that graph (white/grey/black DFS; report any `A -> B -> A` path and emit no edges for that component), then re-assert the edges with native flags. Re-asserting an edge that already exists is a harmless no-op, which keeps the operation idempotent. Reading edges back, or detecting a human-removed edge, would require GraphQL and is out of scope.

## 6. The report (every run)

Print the receipt -- it is the only durable record of what changed, and the coverage check that stands in for a validator:

- **Coverage:** every `active` capability has >=1 issue, or the gap is listed.
- **Traceability:** every managed issue resolves to a current capability, with PRD trace and both versions stamped.
- **DAG integrity:** the desired dependency graph is acyclic (or the cycle is named).
- **Lock:** the version-lock gate passed (asserted in preflight).
- **Drift:** every changed-fingerprint capability is accounted for by one of the actions above -- created, updated, flagged, closed, or followed-up.

Summarize counts: created, updated, flagged, closed, follow-ups, skipped.
