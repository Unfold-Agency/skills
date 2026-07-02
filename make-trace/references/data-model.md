# make-trace data model -- tiers, links, ledger, no-op guard

The durable contract the generator (`scripts/build_trace.py`) implements. Every
edge is DERIVED from a field the upstream skills already maintain; make-trace maps
nothing by hand and writes nothing back to the specs or GitHub.

## The four tiers

| Tier | Source | Node id | Kind field |
|---|---|---|---|
| Objectives | `docs/product/overview.md` `goals` | `G-NNN` | `kind` = business \| user |
| Requirements | `docs/product/features/<slug>.md` `requirements` | `FR/IR/NFR/CR-<PREFIX>-NNN` | id prefix |
| Architecture | `docs/product/arch-data.yaml` | `C-NNN` (components), `ADR-NNNN` (decisions), `INTG-<norm-name>` (integrations) | `C` / `ADR` / `INTG` |
| Issues | `gh issue list --state all` | `#N` | `issue` |

Integrations have no id in `arch-data.yaml`, so a stable `INTG-<normalized-name>`
id is synthesized from the integration name (lowercased, non-alphanumerics folded
to `-`). Tombstoning survives as long as the name is stable.

## The edges (child -> parent; "from" is closer to Issues)

All edges are re-derived every run from each node's stored `links`, so a tombstoned
node still draws its former chain.

- **requirement -> objective**: the requirement's feature declares
  `supports: [G-NNN]` (a make-spec feature-level field); every requirement in that
  feature links to those goals.
- **architecture -> requirement**:
  - **ADR -> requirement**: union of the ADR's `governs: [req ids]` (from
    `arch-data.yaml`) and every requirement whose `governed_by` names that ADR.
  - **component / integration -> requirement**: inherited -- a component links to
    the requirements covered by the ADRs in its `governed_by`. A component with no
    governing ADR (or whose ADRs govern nothing) floats, unwired.
- **issue -> requirement / ADR**: the `make-issues:meta` block's `trace_req` and
  `trace_adr`. An **amendment** issue (empty `trace_req`) instead links to the goals
  its `feature` anchor supports, so it still rolls up to objectives.

A trace id that resolves to no node is recorded as an **orphaned ref** (surfaced in
the header), not wired.

## Status and roll-up

Issue status mirrors `do-work/scripts/select_work.py` exactly, so the map agrees
with the build loop:

| GitHub state | Map status | Color |
|---|---|---|
| closed + `COMPLETED` | done | green |
| open + started (assignee / closing PR / `status:doing`) | doing | blue |
| open, not started | todo | gray |
| closed + `NOT_PLANNED` | dropped | purple, dimmed |

Roll-up: each **present, non-dropped** issue is propagated to every ancestor. A
parent is `done` when all beneath are done, `doing` when any has started, `todo`
when none, `none` when it has no issues. `pct = round(100 * (done + 0.5*doing) / total)`.
Dropped and deleted issues render but never move a parent's numbers.

Dimming (`dim: true`): spec items with `status` in `{superseded, deferred,
deprecated, rejected, dropped, obsolete}`. Tombstoned nodes render struck through
with a dashed connector regardless of status.

## The ledger (`docs/product/traceability/data.json`)

`data.json` IS the ledger and the single source of truth; `index.html` is rendered
from it. Shape:

```
{
  "meta": { "generatedAt", "repo", "projectVersion", "archVersion", "totals", "orphanedRefs" },
  "columns": [ { "key", "label", "groups": [ { "id", "label", "nodeIds", "collapsible?" } ] } ],
  "nodes": {
    "<id>": {
      "id", "tier", "kind", "title", "full", "status", "dim",
      "state": "present" | "deleted",
      "group": { "col", "id", "label" },       // where it renders
      "links": { ... },                         // outgoing refs, for edge re-derivation
      "color", "pct", "counts",                 // computed roll-up (issues: color only)
      "number", "url", "badges", "traced"       // issues only
    }
  },
  "edges": [ { "from", "to" } ]
}
```

### Merge (additive, never destructive)

Every run:

1. Load the prior ledger's `nodes` (if any).
2. Build the current node set from the live sources.
3. **Upsert** each current node -> `state: present`, refreshing its data (this is how
   changes and renumbering land).
4. **Tombstone** each prior node absent from the current set -> `state: deleted`,
   keeping its last-known data (so its chain still renders). A node that returns
   resurrects to `present`.
5. Re-derive edges from the merged node set (present + deleted); recompute roll-up
   over present, non-dropped issues; rebuild the columns.

Deleted nodes are placed back in their stored group; if that group is gone (e.g. a
whole feature was removed) they appear in a leftover group at the end of the column.

### Fail-closed emptiness guard

A source that previously contributed present nodes but yields zero now is almost
always a bad `--spec-dir` or a failed fetch, not a real deletion. The run aborts
(exit 2) and writes nothing when the objectives, requirements, or issues tier goes
non-empty -> empty. Architecture is exempt when there is no `arch-data.yaml` (lite
mode) but guarded when a present arch file yields nothing. `--allow-empty` overrides
to confirm a genuine emptying (which then tombstones the vanished nodes).

`gh` failing entirely (non-zero, bad JSON, not installed) aborts before any write --
never tombstoning every issue on an auth blip.

## Byte-identical no-op guard

The only volatile field is `meta.generatedAt`. The generator builds the ledger with
`generatedAt = null`, serializes canonically (`json.dumps(..., indent=2,
sort_keys=True)`), and compares to the previous file with its `generatedAt` nulled.
If they match, the previous timestamp is reused, so `data.json` and `index.html` are
byte-for-byte identical -- an unchanged regeneration produces no git diff. No
per-node timestamps are stored, so nothing else can drift on a no-op.

## Privacy

`index.html` is fully self-contained: the data is inlined at the `__DATA__`
placeholder with `<` escaped to `<` (a stray `</script>` in the data cannot
break out of the tag), and there are no external requests -- no CDN scripts, fonts,
styles, images, or fetches. The only outbound URLs are the GitHub issue hyperlinks
(`target="_blank"`), which are user-clicked, not fetched. Open it locally or from
the committed file; it publishes nothing.
