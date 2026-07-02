# Reconciliation (create + sync)

How to bring an existing set of GitHub issues back in line with changed specs. The prime directive: **the specs are canonical; the issue is a projection.** You never edit a requirement in an issue to change scope -- you change the feature spec and re-sync. And you **never overwrite a human's notes**. Reconciliation reasons about one kind of drift -- a feature **requirement** vs. its issue -- plus a light anchor check for amendments (below). Generate mode is this engine run against an empty existing set. Read `references/scoping-and-modes.md` first for the precondition, how a run is scoped, and the two provenance modes.

**Detection is global; writes are scoped.** `scripts/analyze.py` always loads the **whole** spec set and compares every requirement's live fingerprint against its issue's stamped one -- an **exhaustive** scan, never CHANGELOG-scoped, so a stale or missing CHANGELOG entry can never hide a real change, and an unselected feature can never be misread as "removed from specs" and mass-closed. `--scope` (feature slugs and/or requirement ids) bounds only which ops are **actionable**: drift outside the scope is still detected and **reported** (`plan["out_of_scope"]`), just not written. STALE/CLOSE and REFACTOR only fire for an issue whose feature is in scope. Every op carries a stable idempotency key, and the refactor fan-out is capped. The committed watermark records "since the last sync" for the report; the CHANGELOG is the human narrative of the delta, not an input to the scan. `analyze.py` computes the whole plan read-only and is the **hard gate** -- no GitHub write happens until it exits 0 or a human approves its remediation report.

## 1. Pull the issues and run analyze

Pull the managed issues once:

```
gh issue list --repo <owner/name> --label make-issues --state all --limit 1000 \
  --json number,title,state,stateReason,labels,body,assignees,closedByPullRequestsReferences,milestone,updatedAt,url \
  > issues.json
```

Then run the planner -- this is the gate. Pass `--scope` for a just-in-time run (empty = act on everything); `--promote` to promote an amendment (below):

```
python scripts/analyze.py --spec-dir docs/product --issues issues.json --scope checkout,cart --max-refactors 10
```

It exits **0** when the plan is clean and safe to execute, or **1** on **blocking drift** (a malformed meta block, a refactor fan-out over the cap, or an invalid `--promote` target). On exit 1, **do not write anything**: present its remediation report and get a human to resolve or approve it first. The plan is also available as JSON (`--json`) for the review pass.

Internally analyze reads the `provenance` first (absent == spec) and builds two views: the **match map** `by_req[req_id] -> [issue, ...]` for spec issues (matched on the meta block's `trace_req` between `<!-- make-issues:meta -->` and `<!-- /make-issues:meta -->` in `body`), and a separate **amendments** list (matched by feature anchor, not a requirement). If the meta block is missing or malformed, it does **not** auto-recover from the prose body -- the `## Traceability` table is free prose, not a machine contract. It records the issue as **blocking drift**; a human re-stamps the meta block and re-runs. A spec issue with an empty/string `trace_req`, or an amendment with no `feature` anchor, is blocking drift. One requirement may map to more than one issue (sliced into several) -- all are kept. The per-requirement fingerprint comes from `item_fingerprint.py docs/product`; the ADR statuses (for the refactor trigger) from the `decisions/ADR-*.md` frontmatter (legacy fallback: the pre-migration `arch-data.yaml` index).

## 2. The watermark and the CHANGELOG delta

`docs/product/.make-issues-sync.json` is a committed, per-feature watermark -- the marker that makes "since the last sync" a fact, not a vibe:

```json
{
  "checkout": { "feature_version": "1.2", "last_changelog_entry": "2026-06-20 -- v1.2" },
  "cart":     { "feature_version": "1.0", "last_changelog_entry": "2026-06-01 -- v1.0" }
}
```

`analyze.py`'s **detection** is exhaustive: every run it walks every requirement and compares its live fingerprint against the matching issue's stamped one. It does **not** read the CHANGELOG, and neither the watermark nor `--scope` narrows this scan -- `--scope` bounds only which ops are written, never what is detected. A full fingerprint scan is the safe choice, because a stale or missing CHANGELOG entry can never hide a real change. The CHANGELOG's structured **Added / Modified / Removed** id lists are the human narrative of the delta (and what you write into the report), not an input that narrows the scan. The watermark records the last sync point per feature; after a successful run, **advance the watermark** to each feature's current `feature_version` and the latest CHANGELOG entry, and commit it. The finite requirement set and the refactor fan-out cap are the real bounds.

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

And the **ADR-driven** trigger, independent of the requirement text:

```
governing ADR superseded/deprecated AND the issue is merged -> REFACTOR
    (the decision behind shipped work flipped, even if the requirement text didn't)
```

**REFACTOR** is the action the merged/shipped state needs: a MODIFIED or REMOVED requirement whose issue is completed/merged, or a requirement whose governing ADR was superseded and whose issue merged, opens a **refactor issue** -- always HITL, labelled `refactor`, traced back to the requirement and the superseding ADR, and linked to the issue it reworks. It is never an auto-edit and never a silent close: shipped code only changes under a human's eye.

Each action is **keyed on fingerprint equality** and carries a **stable idempotency key** (`action:req:fingerprint[:issue]`), so the whole sync is idempotent: a re-run with no spec change skips everything, creates no duplicates, and reproduces the same keys.

### The scope guard on close/refactor

The decision tree above runs for **every** requirement (detection is global), but a resulting STALE/CLOSE or REFACTOR only becomes an **actionable op** when the issue's feature is **in scope** -- otherwise it is recorded in `plan["out_of_scope"]` and reported, not written. Because `analyze.py` always loads the complete spec set, an orphan (an issue whose `req_id` is gone from the specs) is a true orphan, never a scoped-load false positive -- but its close still waits until its feature is selected. This is the guard that makes a just-in-time run safe: a run scoped to `checkout` can never close `cart`'s issues.

### Amendments are provenance-exempt

An issue with `provenance: amendment` is **not** a requirement projection, so the decision tree above does not apply to it. The reconciler:

```
amendment, feature anchor still exists   -> SKIP (leave the body alone; human-owned)
amendment, feature anchor gone           -> COMMENT-AND-FLAG (label orphaned); a human
                                            re-anchors or closes -- NEVER auto-closed
```

An amendment is never STALE/CLOSE'd, never REFACTOR'd, and its body (authored, not embedded) is never clobbered -- it is human-owned like the human region. The only drift it can have is a **lost anchor**: its `feature` no longer exists in the specs.

### PROMOTE: an amendment becomes a spec issue

When a requirement later covers an amendment, promote it in place instead of creating a duplicate -- **operator-confirmed**, never a silent fuzzy match:

```
python scripts/analyze.py --spec-dir docs/product --issues issues.json --promote <N>=<REQ-ID>
```

analyze validates `<REQ-ID>` is an **active** requirement (else blocking drift) and plans a `PROMOTE` op. The executor rewrites the issue's managed regions to the spec form -- set `trace_req: [<REQ-ID>]`, flip `provenance` to `spec`, drop the `amendment` label, embed the requirement text + EARS criteria + ADR snippets, stamp the fingerprint -- while preserving the human region. Thereafter it reconciles like any spec issue. This closes the mode overlap: the same work never lives as both an amendment and a fresh traced issue.

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

Phasing is **optional** in the new overview. When `overview.md` carries a `phasing` list, each issue belongs to a GitHub milestone -- one per phase, title `Phase <N>: <name>`. This is a **separate axis from the fingerprint decision tree** (§4), and it runs on every sync regardless of fingerprint, exactly like the dependency-edge re-assertion in §7. Phase is sequencing, not contract -- it lives only in the overview's `phasing`, keyed by feature slug, never on a requirement, so a re-phase never changes a per-requirement fingerprint and never trips `needs-rebase`/`spec-drift`.

1. **Ensure the milestones exist:** `phase_milestones.py docs/product/overview.md --ensure --repo <owner/name>`. Idempotent; it creates missing milestones and patches a renamed/relabelled one in place (matched on the leading `Phase <N>`), so re-sequencing never orphans a milestone its issues still hang off.
2. **For each managed issue**, compute its intended phase from `feature_to_phase` and its meta `feature` slug. Compare to the issue's live `milestone` (from the JSON above).
3. **If they differ, re-assign silently** -- `gh issue edit <N> --repo <owner/name> --milestone "Phase <N>: <name>"` -- and record it in the report. Do **not** add a flag: a moved feature is a re-sequence, not a scope change. An issue whose feature is not in the plan keeps whatever milestone it has and is reported.
4. An overview with **no `phasing` plan** skips this pass entirely; existing milestones are left untouched.

## 9. The report and the dedicated issues log (every run)

Print the receipt AND append it to `docs/product/ISSUES-CHANGELOG.md`. The printed receipt is the coverage check that stands in for a validator; the ledger is the durable, honest record of what make-issues did over time. It is a **separate** file from make-spec's spec `CHANGELOG.md` (which records spec changes): this one records **issue operations**.

The receipt must be **honest about scope**. A scoped or dirty run never prints an unqualified green:

- **Scope:** what was acted on ("features: checkout" or "ALL -- full run").
- **Coverage:** every in-scope `active` requirement has >=1 issue, or the gap is listed. On a scoped run this is **PARTIAL** -- name the in-scope features and how many requirements in other features were not acted on.
- **Out-of-scope drift:** the count and list from `plan["out_of_scope"]` -- drift detected by the global census but not written this run (widen `--scope` or run `--all` to act).
- **Traceability:** every managed issue resolves to a current requirement (spec) or a valid feature anchor (amendment), with ADR trace and the source `feature_version` stamped.
- **DAG integrity:** the desired dependency graph (from `depends_on`, mirrored in the issue body) is acyclic (or the cycle is named).
- **Integrity:** the scoped fingerprint gate passed for the selected specs. If preflight downgraded a dirty unselected/project file to a warning, say "integrity: PARTIAL (unselected specs mid-edit)".
- **Drift:** every changed-fingerprint in-scope requirement is accounted for by an action -- created, updated, flagged, refactored, closed, promoted, or followed-up.
- **Phases** (when the overview has a plan): every active in-scope phase has >=1 issue and every issue has a milestone, or the gap is named; plus any phase-spanning feature filed under its latest phase.
- **Watermark:** each feature's last-synced version (read for the report), and the new watermark the executor writes after the run.

Summarize counts: created, updated, flagged, closed, refactors, refactor-tracking, promoted, skipped; and, with a plan, milestones created/updated and issues re-assigned to a new phase. Report any refactor fan-out truncation explicitly.

### The dedicated ledger format

`docs/product/ISSUES-CHANGELOG.md` is a Keep-a-Changelog-style ledger, newest entry on top; never rewrite old entries. Append one dated entry per run:

```markdown
## <YYYY-MM-DD> -- scope: <features/reqs, or ALL> -- coverage: <FULL | PARTIAL> -- integrity: <CLEAN | PARTIAL>

**Created**
- #142 FR-CHK-001 (feature: checkout)
- #143 amendment "rate-limit login" (anchor: checkout)

**Updated**
- #118 FR-CHK-004 -- fingerprint changed; managed regions re-stamped

**Flagged / Closed / Refactored / Promoted**
- #90 FR-CHK-009 -- flagged spec-drift (started + hitl)
- #77 amendment -> promoted to FR-CHK-007 (provenance now spec)

**Out-of-scope drift (detected, not acted on):** 2 -- FR-CART-001, CR-CART-001
```

Keep the date and scope line scannable. The lists mirror the run's op counts; omit an empty section. This ledger is what a teammate reads to answer "what happened to my issues?" -- so a partial run must say PARTIAL, not read like a full sync.
