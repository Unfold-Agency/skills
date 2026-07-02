---
name: make-issues
description: Just-in-time, spec-anchored GitHub Issues. Point it at the feature(s) or a description you want tickets for and it creates or reconciles exactly that slice -- each issue traced back to the spec set -- then records what it did in a dedicated issues log. Use this skill whenever the user wants to make issues or tickets for some feature(s), break a slice of the work into work items, add a quick issue for something not yet in the specs, push the plan to GitHub, or reconcile existing issues after a spec or ADR change. Trigger it even if the user says "make issues for checkout," "create the tickets," "add an issue for X," "plan this work," or "sync the issues with the latest spec." It runs AFTER the planning layer and needs a spec set (make-spec, ideally make-arch); if none exists it stops and points there. Do NOT use for authoring the overview/features (upstream -- use make-spec) or the architecture (upstream -- use make-arch); this skill consumes docs/specs and writes to GitHub.
---

# Make issues

Turn a chosen slice of an existing `docs/specs/` spec set into GitHub Issues that
humans and coding agents can act on, then keep those issues honest as the specs
change. The job is **traceability and stale-resistance**, not just decomposition.
This is the lane after the planning layer -- `/make-spec` (the WHAT/WHY) and
`/make-arch` (the HOW) come first. make-issues is **just-in-time**: you point it at
the feature(s), or a description, you want tickets for now, and it creates or
reconciles exactly that slice.

Unlike the upstream skills, this skill has **no local data file and no validator**.
The output is GitHub state: the issues, their labels, and a machine-readable meta
block embedded in each issue body ARE the index. You query them live with
`gh ... --json`. The check that stands in for a validator is the **analyze plan** (a
read-only reconcile planner and hard drift gate) plus a coverage/reconciliation
**report** printed every run and appended to a dedicated issues log.

The doctrine that governs everything: **the specs stay canonical; an issue is a
derived projection.** To change scope you change the feature spec and re-sync -- you
never edit the requirement inside an issue. Every issue traces back to the spec set:
a **spec** issue to the feature requirement it serves (and its governing ADRs); an
**amendment** issue -- work added on demand -- to a feature/goal/ADR **anchor**. No
issue without a trace. Each issue is a **self-contained vertical slice** -- it embeds
(or, for an amendment, authors) the requirement text, its acceptance criteria, its
verification entries (the proof plan, schema 1.1+), and a one-line snippet of each
governing ADR, so a builder need not open the specs to act. Engineers may still add
notes in the issue's human region, which sync never overwrites.

## The precondition: this skill runs after make-spec

make-issues assumes `docs/specs/` already exists. **If there is no spec set it
stops** and sends you to `/make-spec` (and `/make-arch`). It never creates
un-anchored issues -- for ad-hoc GitHub issues with no spec behind them, use a
different tool. An on-demand add here is a **quick amendment, not a rewrite**: it
still anchors to the real features/goals/ADRs the spec set already holds.

## The source: docs/specs/

The planning layer is a layered spec set, not a PRD+TDD pair. Each spec is a single
Markdown file whose **YAML frontmatter** carries the structured contract (make-spec
emits one file per document -- there is no separate `*-data.yaml`); `arch-data.yaml`
is make-arch's own plain-YAML file:

- `overview.md` -- the lean PRD: `meta` (project_version, mode, status, fingerprint), `goals` (G-NNN), `scope`, `non_goals`, a `feature_index` (rows `{slug, prefix, title, feature_version, status, appetite}`), and an OPTIONAL `phasing` list.
- `features/<slug>.md` -- one per feature: `meta` (slug, prefix, status, feature_version, fingerprint) plus a `requirements` list. **The requirement is the work item.** Each carries `id` (e.g. `FR-CHK-001`), `name`, `kind`, `description`, EARS `acceptance_criteria` (order-significant), `verification` (schema 1.1+: `{method, check, covers}` proof entries -- `demo`/`inspection` methods signal HITL, see slicing-and-review.md), `governed_by` (ADR ids), `depends_on` (requirement ids, may cross features), `interface`, advisory `priority`/`architecture_hints`/`related_files`/`notes`, and a lifecycle `status`.
- `arch-data.yaml` -- architecture plus a `decisions` index (ADR rows `{id, title, status, scope, superseded_by, confidence}`); full prose in `decisions/ADR-NNNN-*.md`.
- `CHANGELOG.md` -- make-spec's Keep-a-Changelog ledger of **spec** changes (Added/Modified/Removed id lists). make-issues reads it as the human narrative of the delta; it does not write it.

The integrity gate is the **fingerprint gate** (below), now scoped ("a1").

## Files in this skill

- `assets/issue-body-template.md` -- the issue body: managed regions (prose, `meta`, `changelog`) plus a `human` region sync never overwrites. Includes the amendment variant (authored criteria, `provenance: amendment`, a feature anchor). Read it before creating issues; follow the authoring comments, then strip them.
- `assets/labels.yaml` -- the label scheme (provenance `make-issues`/`amendment`, autonomy, reconciliation flags, refactor) and the meta-block contract. Traceability and source version live in the issue body, not as labels.
- `references/scoping-and-modes.md` -- **read this first**: the spec-set precondition, how to scope a run (description / flags / checklist), the two provenance modes, amendment authoring, the a1 dirty-spec gate, honest receipts, and promotion.
- `references/slicing-and-review.md` -- how to cut requirements into thin work items, author an amendment, mark AFK/HITL (afk requires criteria), assemble trace fields, and run the review gate before any write.
- `references/reconciliation.md` -- the match map, the analyze plan, the decision tree (including REFACTOR and PROMOTE), scope-writes/global-detection, the orphan-close guard, amendment exemption, managed-region surgery, and the report + dedicated ledger.
- `scripts/gh_preflight.py` -- the preflight gate (read-only): auth, gh version, the **spec-set precondition**, the **scoped fingerprint gate**, repo, mode, and missing labels. Run it first, every run.
- `scripts/item_fingerprint.py` -- per-requirement fingerprint over the contract-bearing (IN) requirement fields; the hash stamped on each spec issue and compared on sync.
- `scripts/analyze.py` -- the bounded reconcile planner + hard drift gate (read-only, no network). Detection is global; `--scope` bounds writes; `--promote` promotes an amendment. It caps the refactor fan-out and exits nonzero on blocking drift. **No GitHub write happens until analyze passes.**
- `scripts/phase_milestones.py` -- maps the overview's OPTIONAL `phasing` plan (feature -> phase -> milestone) and, with `--ensure`, creates/patches them. No `phasing` -> no milestones.

## Preflight (always, first action)

Run the gate and stop on any failure before touching GitHub. Pass the scope you are
about to act on so the dirty-spec gate can be advisory outside it:

```
python scripts/gh_preflight.py --spec-dir docs/specs --scope <feature-slugs and/or req-ids>
```

It checks, in order: `gh auth status`; **gh >= 2.94.0** (native dependency/type
flags -- below that, stop and tell the user to `brew upgrade gh`); the **spec-set
precondition** (no `docs/specs/` -> stop, go to `/make-spec`); the **scoped
fingerprint gate**; a git work tree with a resolvable `owner/name`; and the existing
managed issues, which pick the mode. It reports any missing static labels; create
them with `gh label create <name> --color <hex> --description "..." --force` from
`assets/labels.yaml` (including the `amendment` label).

**The scoped fingerprint gate (a1).** Every spec file stores a `meta.fingerprint`
over its CONTRACT content; preflight recomputes each. A **selected** feature that is
mid-edit (stored != recompute) **fails** the gate -- you must not project a
half-saved requirement into a traced issue; re-stamp via `/make-spec` or deselect
it. A dirty **unselected** feature, or a dirty overview/arch, is a **warning**, not
a block (a scoped run reads each feature's version from its own file). A **full run**
(`--all`) still fails on any dirty spec -- the original fail-closed guarantee for the
run that claims to cover everything.

It also prints an **approval advisory** (non-gating): the gate can pass while the
overview is still `draft`. If preflight warns it is not `approved`, surface that and
get explicit confirmation before creating anything.

## Selecting the slice

Read `references/scoping-and-modes.md`. In short:

- **A description** -- scope tightly, skip the checklist. Because a description can
  either *select* existing spec work or *author* a new amendment, resolve which
  **explicitly** (search for a strong requirement/feature match and ask), never by
  silent inference.
- **Explicit flags** -- `--feature=<slug>`, `--req=<ID>`, `--all` (repeatable),
  mapping to `analyze.py --scope`. `--all` restores the exhaustive behavior.
- **The checklist (bare run default)** -- present the `feature_index` as a checklist
  (title, status, requirement count, how many already ticketed) plus a final "make
  all", and turn the selection into the scope.

Both create and reconcile run on the selected slice. Whether managed issues already
exist decides only how each requirement branches (create vs update/flag/close);
preflight reports the count so you know.

## Scope writes, keep detection global

`analyze.py` always loads the **whole** spec set and computes drift for every
requirement -- detection is global, so a stale CHANGELOG can never hide a change and
an unselected feature can never be misread as "removed from specs" and mass-closed.
`--scope` bounds only which ops are **actionable**; drift outside the scope is
detected and **reported** (`plan["out_of_scope"]`), never written. STALE/CLOSE and
REFACTOR only fire for an issue whose feature is in scope.

## The two provenance modes

- **spec** (default; absent == spec) -- the issue projects a requirement: embed its
  text, EARS acceptance criteria, interface, and governing-ADR snippets; stamp the
  per-requirement fingerprint; reconcile by the full decision tree.
- **amendment** -- added on demand, anchored to a feature/goal/ADR, body authored
  (not embedded), no requirement fingerprint, `amendment` label. Reconciliation
  never orphan-closes, refactors, or clobbers it; it only flags a lost anchor.
  **afk requires acceptance criteria** -- a criteria-less amendment must be `hitl`.
  When a requirement later covers it, **PROMOTE** it in place (operator-confirmed)
  rather than creating a duplicate. See `references/scoping-and-modes.md`.

## Workflow

1. **Preflight** with `--scope` (above). Stop on any failure; heed warnings.
2. **Read the specs** for the selected slice: the `features/<slug>.md`
   `requirements` you will slice, the `overview.md` goals + feature_index (+ optional
   `phasing`), and `arch-data.yaml` (ADR index, for `trace_adr` and one-line
   snippets). Read `references/slicing-and-review.md`.
3. **Assemble the plan.** For spec work, slice each `active` requirement into thin
   items and fill the template (requirement text + EARS criteria + interface + ADR
   snippets + trace fields + fingerprint from `item_fingerprint.py --id <REQ>`). For
   an amendment, author the item against its anchor (see scoping-and-modes.md). Mark
   AFK/HITL honestly -- afk requires criteria.
4. **Run analyze -- the hard gate.** `python scripts/analyze.py --spec-dir docs/specs
   --issues <gh-json> --scope <tokens> [--promote N=REQ] [--max-refactors N]`. It
   exits 0 on a clean plan, or 1 on blocking drift (malformed meta, refactor
   overflow, invalid promote target). **No GitHub write until it exits 0** or a
   human approves its remediation report.
5. **Review pass (the human gate).** Present the plan -- created/updated/flagged/
   closed/refactored/promoted within scope, plus the out-of-scope drift and the
   coverage/integrity qualifier -- and iterate to approval. Create nothing first.
6. **Execute** within scope, in dependency order (blockers first). For UPDATE,
   touch only the managed regions and splice the human region back byte-for-byte.
   For a `phasing` plan, ensure milestones first, then assign each issue its phase.
7. **Report + ledger.** Print the receipt and append it to
   `docs/specs/ISSUES-CHANGELOG.md`; advance the watermark.
8. **Refresh the traceability map (if make-trace is present).** After a successful
   sync, regenerate the traceability map so it reflects the issues you just created
   or updated -- run `/make-trace`, or call its generator directly
   (`python <make-trace>/scripts/build_trace.py`, locating `make-trace/` as a sibling
   skill directory). It reads `docs/specs/` + the live issues and rewrites the
   self-contained `docs/traceability/` artifact; a no-op regeneration is byte-identical,
   so an unchanged map produces no diff. This step is **non-fatal**: if make-trace is
   not installed, skip it with a one-line note (the sync itself is already complete).

## Report + the dedicated issues log (every run)

Always print the receipt AND append it to `docs/specs/ISSUES-CHANGELOG.md` (the
dedicated issues-operations ledger, separate from make-spec's spec `CHANGELOG.md`).
See `references/reconciliation.md` §9 for the entry format. It is **honest**: a
scoped or dirty run records **partial** coverage and the out-of-scope drift, never
an unqualified green. Cover: coverage (every in-scope active requirement has an
issue, or the gap is named; partial when scoped), out-of-scope drift, traceability,
DAG integrity, integrity (the scoped fingerprint gate; partial if unselected specs
are mid-edit), and drift (every changed in-scope requirement accounted for).
Summarize counts: created, updated, flagged, closed, refactors, refactor-tracking,
promoted, skipped; with a plan, milestones created/updated and phase re-assignments.
Report any refactor fan-out truncation explicitly -- never silently drop.

## Honest limits

State these plainly; do not pretend past them.

- **A spec set is required.** make-issues runs after `/make-spec`; with no
  `docs/specs/` it stops. It does not create un-anchored issues.
- **Scope bounds writes, not detection.** A scoped run detects drift everywhere but
  acts only in scope, and says so ("coverage: PARTIAL"). To reconcile the whole
  project, run `--all`. Do not read a scoped run's green as "everything is synced."
- **Amendments are human-owned.** Reconciliation never clobbers, orphan-closes, or
  refactors an amendment; it only flags a lost feature anchor. An amendment is as
  trustworthy as the criteria a human authored on it -- which is why afk requires
  criteria and `do-work` refuses to auto-build a criteria-less issue.
- **Native dependencies need gh >= 2.94.0.** The `--blocked-by`/`--blocking`/
  `--type`/`--parent` flags do not exist below that. Preflight hard-gates it.
- **Dependencies are write-only.** GitHub dependency edges cannot be read back via
  `gh ... --json`. Reconciliation works from the desired DAG derived from
  `depends_on`, verifies it against the issue-body Dependencies mirror
  (white/grey/black DFS; report any cycle), and re-asserts edges idempotently.
- **"Started" is inferred.** No native in-progress state; read from assignee +
  closing-PR. A hand-started branch with no closing PR reads as not-started.
- **No locking, no atomic multi-issue transaction.** A sync is a sequence of `gh`
  calls; a process killed mid-run leaves some issues updated. Re-running reconciles
  it -- every action is keyed on fingerprint equality with a stable idempotency key.
- **Milestones are repo-global and optional.** With a `phasing` plan, phase
  milestones (`Phase N: name`) live at the repo level. No plan -> no milestones. A
  human-removed milestone is silently restored, not detected as drift.
- **The refactor fan-out is capped.** analyze caps refactors at `--max-refactors`
  (default 10), plans one tracking issue for the overflow, and blocks the gate so a
  human triages -- it never opens an overnight cascade.

## Tone and writing rules for issues

Plain words, short sentences, no marketing language. State each work item as one thin
slice with checkable acceptance criteria, self-contained enough to act on without
opening the specs. Never use an em dash in output; use a spaced double hyphen ` -- `
for asides. Write so a coding agent can act on each issue without asking what it means.
