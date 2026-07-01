# ID Grammar & Traceability

IDs are the spine of the whole pipeline. Issues (make-issues), builds (do-work),
and decisions (make-arch) all reference spec IDs, so the grammar is **pinned** and
the validator enforces it (S-002/S-003/S-007). IDs are **never reused or
renumbered**; a cut item becomes `status: superseded` or `deferred`, never deleted
(S-005, no-vanishing).

## The two grammars

### Feature requirements
```
^(FR|IR|NFR|CR)-[A-Z]{2,5}-\d{3,}$
```
- **Kind prefix:** `FR` functional · `IR` integration · `NFR` non-functional ·
  `CR` content.
- **Namespace segment** (`[A-Z]{2,5}`): the feature's uppercased short slug, taken
  from the overview Feature Index. Every requirement in `features/<slug>.md` must
  use that feature's prefix (S-007), and prefixes are unique across the project
  (S-003).
- **Number** (`\d{3,}`): zero-padded, ≥ 3 digits, unique within the feature.

Worked examples:

| ID | Means |
|---|---|
| `FR-CHK-001` | Functional requirement 1 of the **checkout** feature |
| `IR-CHK-002` | Integration requirement 2 of checkout (e.g. fulfillment sync) |
| `NFR-CHK-003` | Non-functional requirement (e.g. encrypt-at-rest) |
| `CR-CART-001` | Content requirement 1 of the **cart** feature |

### Architecture decisions (ADRs)
```
^ADR-\d{4}$
```
- Four digits, assigned in order by make-arch: `ADR-0001`, `ADR-0002`, ...
- A requirement that an architecture decision governs links to it via
  `governed_by: [ADR-0001]` in its frontmatter (the machine link). The feature
  spec stays WHAT-only -- it never restates the decision.

### Overview goals
```
^G-\d{3,}$
```
- `G-001`, `G-002`, ... Goals carry the measurable success metrics in the overview.
- A feature links to the goal(s) it serves with a top-level `supports: [G-NNN]`
  list in its frontmatter. Every entry must be goal-format and resolve to a real
  overview goal (S-013); it is the feature -> objective edge that make-trace reads.
  Optional, but never invent a goal id to fill it.

## Traceability chains

- **Requirement -> decision:** `governed_by` points a requirement at the ADR(s)
  that decide its HOW. The validator checks the format, and -- once
  `docs/specs/decisions/` exists -- that each ADR id resolves to a real file
  (S-004). Find the governing decision for any feature in ≤ 2 hops: feature spec
  -> its `governed_by` ADR.
- **Requirement -> requirement:** `depends_on` points at prerequisite requirement
  IDs (within or across features). The validator resolves every entry against the
  union of all features (S-004); a cross-feature dependency is a **seam** and is
  governed by the home feature's version (see make-issues / do-work).
- **Feature -> objective:** a feature's `supports: [G-NNN]` names the overview
  goal(s) it advances. The validator resolves every entry against the overview
  goals (S-013); make-trace rolls issue status up this edge to the objectives.
- **Requirement -> issue:** downstream, make-issues stamps each issue with
  `trace_req` (the requirement id), `trace_adr` (its governing ADR), and `feature`
  (the slug), so the affected set of any change is a query, not a hunt.

## The rules in one line

Format-correct, globally unique, feature-namespaced, never deleted. If you are
tempted to renumber, you have found a supersede instead.
