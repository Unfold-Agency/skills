# Scoping & modes (just-in-time make-issues)

make-issues is a **just-in-time** tool: you point it at the slice of work you want
tickets for, now, and it creates or reconciles exactly that slice -- while keeping
the traceability and stale-resistance the pipeline depends on. This reference
covers the precondition, how you scope a run, the two provenance modes, and the
guarantees that keep a scoped run safe.

## The precondition: a spec set must exist

make-issues runs **after** the planning layer. It assumes `/make-spec` (and,
ideally, `/make-arch`) have already produced `docs/product/` -- an `overview.md`, at
least one `features/<slug>.md`, and optionally `architecture.md` + `decisions/`.
Preflight (`gh_preflight.py`) checks this first (`spec_set`): if the spec set is
absent it **stops** and sends you upstream. make-issues never invents un-anchored
issues -- every issue it writes traces back to the spec set. If you only want an
ad-hoc GitHub issue with no spec behind it at all, that is a different tool, not
this one.

This is the reframed contract: make-issues stays spec-canonical, but it no longer
demands you re-run the whole batch to add or fix one ticket. An on-demand add is a
**quick amendment, not a rewrite** (see *Provenance* below).

## Scoping a run: writes are bounded, detection stays global

Every run does the same thing under the hood: `analyze.py` loads the **whole** spec
set and computes drift for **every** requirement -- detection is always global, so
a stale CHANGELOG can never hide a real change, and a scoped run can never mistake
an unselected feature's requirements for "removed from specs." What you scope is
only the **writes**: which creates/updates/closes/refactors actually happen.

Three ways to scope, in order of precedence:

1. **A description argument** -- `/make-issues add rate-limiting to the login flow`,
   or `/make-issues sync the checkout feature`. Tightest focus, no prompt. Because
   a description is ambiguous -- it can *select* existing spec work OR *author* a
   new amendment -- resolve it explicitly, never by silent inference: search the
   requirements/features for a strong match and, on a hit, ask *"scope to the
   existing FR-CHK-001, or author a new amendment under checkout?"* before writing.
2. **Explicit scope flags** -- `--feature=<slug>` (repeatable), `--req=<ID>`
   (repeatable), `--all`. These map straight to `analyze.py --scope <tokens>` and
   `gh_preflight.py --scope <tokens>`. Consistent with sibling `do-work`
   (`--issue`/`--phase`/`--dry-run`), so the grammar is familiar and scriptable.
3. **The checklist (the default for a bare run)** -- with no description and no
   scope flags, present a checklist of the features from `overview.md`'s
   `feature_index` (title, status, how many requirements, how many already have
   issues), plus a final **"make all"** option. The operator ticks what they want;
   the selection becomes the `--scope`. "make all" is the old exhaustive behavior,
   now opt-in.

Always run behind the **review/approval gate** (`--dry-run` shows the plan and
writes nothing). Creating and closing GitHub issues is outward-facing -- present
the plan, get approval, then execute.

### What a scoped run reports (honest receipts)

A scoped run must never look like a full one. The report states its scope up front
and, when partial, says so plainly:

- **Coverage: PARTIAL** -- "acted on features: checkout. N requirements in M other
  features were NOT acted on." Never print an unqualified green "all synced" for a
  slice.
- **Out-of-scope drift** -- analyze lists every drifted requirement outside the
  scope (`plan["out_of_scope"]`): detected, reported, not written. This is how the
  global census stays useful without widening the blast radius.
- **Integrity** -- if preflight downgraded a dirty *unselected* feature (or
  overview/arch) to a warning, say "integrity: partial (unselected specs mid-edit;
  re-stamp before acting on them)."

## Dirty specs (the a1 gate)

The fingerprint gate is now **advisory + scoped**. A dirty spec is one whose stored
`meta.fingerprint` no longer matches its content -- edited in `/make-spec` without
re-stamping. On a run:

- A dirty **selected** feature **fails** the gate. You never project a half-saved
  requirement into a traced issue -- re-stamp via `/make-spec`, or deselect it.
- A dirty **unselected** feature, or a dirty **overview/arch**, is a **warning**,
  not a block. A scoped run reads each feature's version from the feature file
  itself; the overview/arch embeds are advisory context.
- A **full run** (`--all` / "make all") still fails on **any** dirty spec -- the
  original fail-closed guarantee, unchanged, for the run that claims to cover
  everything.

## Provenance: spec vs amendment

Every managed issue carries a `provenance` in its meta block (absent == `spec`, so
pre-existing issues need no migration). It also carries the matching label:
`amendment` for amendments; no provenance label means spec.

- **`provenance: spec`** -- the issue projects a specific requirement. It embeds the
  requirement text + EARS acceptance criteria + governing-ADR snippets, stamps the
  per-requirement `fingerprint`, and is reconciled by the full decision tree
  (CREATE/UPDATE/FLAG/STALE-CLOSE/REFACTOR). This is the default and the bulk.
- **`provenance: amendment`** -- work added on demand that is not (yet) a
  requirement, but still anchored to the existing spec set. An amendment:
  - sets `provenance: amendment`, applies the `amendment` label, and names a real
    `feature` slug as its **anchor** (a goal/ADR may also anchor it);
  - may have an empty `trace_req` and has **no** requirement fingerprint
    (`fingerprint: ""`, `source_version: ""`);
  - has its Requirement + Acceptance-criteria sections **authored** (not embedded
    from a spec) -- and **afk requires acceptance criteria**, so an amendment with
    none must be `hitl` (`do-work` refuses to auto-build a criteria-less issue).

Reconciliation **hard-exempts** amendments: it never orphan-closes, refactors, or
clobbers an amendment body (it is human-owned, like the human region). The only
thing it checks is that the amendment's feature anchor still exists; if the anchor
feature was removed from the specs, it **flags** the amendment (`orphaned`, a
human re-anchors or closes) but never closes it automatically.

## Authoring an amendment

1. Confirm (via the description disambiguation or an explicit choice) that this is
   new work, not an existing requirement.
2. Pick the anchor: the `feature` the work belongs to; optionally the goal it
   serves and any governing ADRs.
3. Fill the amendment variant of `assets/issue-body-template.md`: author the
   Goal, Requirement, and **Acceptance criteria** yourself; set `provenance:
   amendment`, `feature: <slug>`, `trace_req: []` (or the requirement you intend to
   promote to), `fingerprint: ""`, `source_version: ""`.
4. Mark autonomy honestly: `afk` **only** if you authored checkable acceptance
   criteria; otherwise `hitl`.
5. Apply labels `make-issues`, `amendment`, and `afk`/`hitl`. Create it in the
   selected scope like any other issue.

## Promotion: an amendment becomes a spec issue

When `/make-spec` later adds a requirement that covers an amendment, promote it in
place -- do **not** create a duplicate. Promotion is **operator-confirmed**: you
name the pairing, so the fuzzy "did this amendment become that requirement" call is
never made silently.

```
python scripts/analyze.py --spec-dir docs/product --issues issues.json \
  --promote <issue-number>=<REQ-ID>
```

analyze validates the target is an **active** requirement (else blocking drift) and
plans a `PROMOTE` op. The executor then rewrites the issue's managed regions to the
spec form: set `trace_req: [<REQ-ID>]`, flip `provenance: spec`, drop the
`amendment` label, embed the requirement text + criteria + ADR snippets, and stamp
the fingerprint. The human region is preserved. From then on it reconciles like any
spec issue. This closes the mode-overlap the design was careful about: the same work
never lives as both an amendment and a fresh traced issue.

## The dedicated issues log

Every run appends what it did to `docs/product/ISSUES-CHANGELOG.md` (see
`references/reconciliation.md` §9 for the entry format). It is a separate ledger
from the spec `CHANGELOG.md` (which records spec changes, owned by make-spec):
this one records **issue operations**. It reuses the run receipt, and it is honest
-- a scoped or dirty run records its partial coverage, never an unqualified green.
