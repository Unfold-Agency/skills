---
name: make-trace
description: Render one self-contained, private traceability map from the docs/product spec set plus live GitHub Issues -- a four-tier graph (objectives -> requirements -> architecture -> issues) with a computed roll-up of what is not-started / in-progress / done, every edge derived from the spec itself (zero manual mapping). Use this skill whenever the user wants to see traceability, a coverage or status map, "what is done vs left," how issues roll up to goals, which requirements have no issues, or a picture of the whole plan. Trigger it for "show the traceability map," "regenerate the trace," "what's the status of the backlog," "which objectives are done," or "visualize the specs and issues." It is ADDITIVE and never destructive: it accumulates a ledger and marks vanished issues/requirements as deleted rather than dropping them, and a no-op regeneration is byte-identical so it makes no git churn. It runs after make-issues (and do-work) and on demand; it reads docs/product and GitHub and writes only docs/product/traceability. Do NOT use it to author specs (make-spec), record architecture (make-arch), create or sync issues (make-issues), or build code (do-work); this skill only visualizes what those produced.
argument-hint: "[--repo owner/name] [--spec-dir docs/product] [--out docs/product/traceability] [--allow-empty] [--open]"
---

# Make trace

Render one self-contained visual map that answers, at a glance: **which objectives
and requirements are not-started / in-progress / done, and how every live GitHub
Issue rolls up through the spec.** Four tiers, left to right, wired by SVG:

```
Objectives   ->   Requirements       ->   Architecture           ->   Issues
 G-NNN            FR-/IR-/NFR-/CR-         C-NNN / INTG- / ADR-        live GitHub issues
```

This is the **observability** lane. It sits alongside the pipeline rather than
inside it: `/make-spec` (the WHAT), `/make-arch` (the HOW), and `/make-issues` (the
work items) produce the artifacts; make-trace only draws the map. It writes nothing
back to the specs or GitHub -- the sole output is `docs/product/traceability/`.

The doctrine that governs everything: **every edge is derived from the spec itself,
never hand-authored, and the map is additive -- it adds, changes, and updates, but
it never deletes.** A requirement or issue that disappears from the sources is kept
and marked `deleted` (tombstoned), retaining its last-known links so its chain still
renders. Renumber a requirement, change a title, close an issue: all flow through.
Remove one: it stays, struck through.

## What it reads and how the graph is wired

Nothing is mapped by hand. Each edge comes from a field the upstream skills already
maintain (full detail in `references/data-model.md`):

| Tier | Source | Link leftward |
|---|---|---|
| Objectives (`G-NNN`) | `docs/product/overview.md` `goals` | leaf targets (top of the chain) |
| Requirements (`FR/IR/NFR/CR`) | `docs/product/features/<slug>.md` | the feature's `supports: [G-NNN]` -> objectives |
| Architecture (`C-NNN`, `INTG-`, `ADR-`) | `docs/product/architecture.md` frontmatter + `decisions/ADR-*.md` frontmatter (legacy fallback: `arch-data.yaml`) | ADR `governs` / requirement `governed_by`; a component/integration inherits the requirements its governing ADRs cover |
| Issues (`#N`) | `gh issue list --state all` | the `make-issues:meta` block -> `trace_req` / `trace_adr` / `feature` |

- **Issue status** matches what `do-work` sees (the same `select_work` classification):
  closed+completed = **done**, open+started (assignee / closing PR / `status:doing`) =
  **doing**, open = **todo**, closed+not-planned = **dropped**. Labels surface as badges
  (`hitl`, `spec-drift`, `needs-rebase`, `orphaned`, `escalated`, `amendment`, ...).
- **Roll-up** propagates each present issue up to every ancestor: a parent is green
  when all beneath are done, blue when any has started, gray when none, plus a
  progress bar and an X/Y count (doing weighted 0.5). Dropped and deleted issues
  render but never move a parent's numbers.
- **Dimming**: superseded / deferred / deprecated spec items are dimmed; tombstoned
  (deleted) nodes are struck through with a dashed connector.
- **Orphaned refs**: an issue whose `trace_req` / `trace_adr` names an id that is not
  in the current spec is counted (surfaced in the header), not silently wired.

## Workflow

1. **Preflight.** Confirm `gh` is authenticated (`gh auth status`) and a spec set
   exists under `--spec-dir` (default `docs/product`, with `overview.md`). No spec set:
   stop and point at `/make-spec`.
2. **Generate.** Run the generator from the target repo root:

   ```
   python make-trace/scripts/build_trace.py [--repo owner/name] [--spec-dir docs/product] [--out docs/product/traceability]
   ```

   It reads the three sources, merges them into the ledger, computes the roll-up,
   and writes `docs/product/traceability/{index.html, data.json}` (and seeds `README.md` if
   absent). `--repo` is optional (`gh` infers it from the repo); pass `--open` to
   open the map in a browser.
3. **Report.** Relay the one-line receipt: issue totals (done / doing / todo /
   dropped), traced vs untraced, orphaned refs, and tombstones. Point the user at
   `docs/product/traceability/index.html` -- open it locally; nothing is published.
4. **Commit (optional).** The artifact is committed HTML opened locally. Commit
   `docs/product/traceability/` when the user wants the map versioned. A no-op regeneration
   is **byte-identical**, so re-running when nothing changed produces no diff.

## Refresh model

The user chose **skill-run refresh** (no GitHub Action, no bot commits). The map is
regenerated at the end of every `/make-issues` and `/do-work` run (a non-fatal final
step in those skills) and on demand via `/make-trace`. It is therefore only as fresh
as the last skill run; re-run `/make-trace` to pull the latest issue status.

## Safety: additive, and fail-closed

- **Additive / tombstone.** The ledger (`data.json`) accumulates every node it has
  ever seen. A node absent from the current sources becomes `state: deleted`, keeping
  its data so its former chain still draws. A node that returns resurrects to
  `present`. Nothing is ever removed from the map.
- **Fail-closed.** A failed or empty source never tombstones the world. If `gh`
  errors, or a source that previously contributed nodes now yields **zero** (a bad
  `--spec-dir`, a lost auth token, a transient empty fetch), the run **aborts and
  writes nothing**. Confirm a genuine emptying with `--allow-empty`.
- **No-op guard.** When nothing substantive changed, the previous run's timestamp is
  reused so the bytes are identical -- no spurious commits.
- **Private-safe.** The rendered HTML is fully self-contained: data is inlined (with
  `<` escaped so a stray `</script>` cannot break out), and there are **no external
  requests**. Open it locally or from the committed file; it publishes nothing.

## Honest limits

- **Goals wire through `supports`.** Objectives roll up only where a feature declares
  `supports: [G-NNN]` (a make-spec field). A feature with none leaves its goals
  un-wired -- add `supports` in `/make-spec` to connect them.
- **Components / integrations have no direct issues.** No issue traces to a component,
  so they carry no roll-up color; they show structural context and connect to the
  requirements their ADRs govern (useful for the highlight chain).
- **Freshness is skill-run only.** Between runs the status can go stale; re-run
  `/make-trace` (or let the next `/make-issues` / `/do-work` run refresh it).

## Files

- `scripts/build_trace.py` -- the generator (reads specs + issues, merges the ledger, renders).
- `assets/template.html` -- the self-contained vanilla-JS/SVG renderer (`__DATA__` placeholder).
- `assets/README-traceability.md` -- seeded into `docs/product/traceability/README.md` for viewers.
- `references/data-model.md` -- the tier / link / ID contract, the ledger schema, and the no-op guard.
- `scripts/tests/` -- pytest suite + fixtures (`python -m pytest make-trace/scripts/tests`).
