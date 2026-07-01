---
name: make-data-flows
description: Generate and maintain per-feature data-flow and user-flow diagrams (Mermaid) embedded directly in each docs/specs feature file, so engineers can see how a single feature moves data and walks a user. Use this skill after make-spec and make-arch, whenever the user wants flow diagrams, data-flow or user-flow documentation, "how does this feature actually work", or wants to refresh diagrams after requirements changed. Trigger it for "diagram the data flow", "add user flows", "show how checkout works step by step", or "update the flows for feature X". It runs on demand and targets a specific feature (--feature) to avoid overworking minor edits. It is ADVISORY -- it embeds diagrams in feature bodies (out of the fingerprint) and never gates the build. Do NOT use it to draw the system architecture (that is make-arch) or to author requirements (make-spec).
argument-hint: "[--feature=<slug>]... [--all] [--check] [--force] [--spec-dir docs/specs]"
---

# Make data flows

Give engineers a picture of **how one feature works** -- the data that moves through
it and the path a user walks -- as Mermaid diagrams embedded in that feature's own
spec file. It reads the `make-spec` requirements (and, where present, the `make-arch`
component names) and writes one managed region into each `features/<slug>.md` **body**.

```
docs/specs/features/<slug>.md
  ---
  (frontmatter contract -- NEVER touched by this skill)
  ---
  # Feature ... (human narrative -- preserved byte-for-byte)

  <!-- make-data-flows:flows -->        <- the one managed region this skill owns
  ...data-flow + user-flow diagrams...
  <!-- /make-data-flows:flows -->
```

**The doctrine: diagrams illustrate the WHAT, they never redefine it.** The requirement
is the contract; a flow is a picture of it, traced back to the requirement id(s) it
covers. Because the region lives in the body, it is **out of make-spec's fingerprint**
(which hashes only the frontmatter), so embedding a diagram can never move a feature's
version or trip the S-006 integrity gate. This skill is **advisory**: it refreshes
diagrams and never blocks `make-issues` or `do-work`.

## When it runs, and what it is not

Run it **after** `make-spec` (and normally `make-arch`), on demand. It is not part of
the build gate -- a stale or missing flow never stops a build; it is an engineering aid
you refresh when a feature's contract moves. It draws the **feature altitude**; the
**system altitude** (C4 context/container, the system ERD, cross-feature sequences) is
`make-arch`'s. See `references/boundary-with-arch.md` for the crisp rule.

## Modes

- **Kickoff** -- a feature has no flows region yet. Generate data + user flows from its
  requirements. Read `references/kickoff.md`.
- **Amend** -- a region exists. The skill compares the feature's current `feature_version`
  to the one stamped in the region: unchanged -> **SKIP**; changed -> **REGENERATE**.
  This is what lets `--feature` targeting avoid overworking minor edits -- an advisory
  edit (priority, notes) never moves the version, so it never regenerates. Read
  `references/amend-and-staleness.md`.

## Files in this skill

- `assets/flow-region-template.md` -- the exact marker grammar and a worked region.
- `assets/diagram-kinds.md` -- which Mermaid kind to use for a DATA flow vs a USER flow.
- `references/boundary-with-arch.md` -- feature altitude vs system altitude.
- `references/kickoff.md` -- generating flows for a feature that has none.
- `references/amend-and-staleness.md` -- the SKIP-vs-REGENERATE oracle and safe updates.
- `references/subagent-brief.md` -- the exact brief for the per-feature worker.
- `scripts/flow_status.py` -- the read-only planner + gate (CREATE / REGENERATE / SKIP).
- `scripts/embed_flows.py` -- the deterministic writer (region surgery + no-op guard).
- `scripts/validate_flows.py` -- run after every embed (DF-001..DF-006).
- `scripts/flowlib.py` -- shared marker/frontmatter helpers.

## The plan -> generate -> embed -> validate loop

1. **Preflight.** Confirm a spec set exists under `--spec-dir` (default `docs/specs`,
   with `features/*.md`). None -> stop and point at `/make-spec`.
2. **Plan (the gate).** `python scripts/flow_status.py docs/specs [--feature <slug>]...`.
   It loads the whole spec set (detection is **global**), prints CREATE / REGENERATE /
   SKIP per feature, and lists what is **actionable** in scope. `--feature` bounds only
   what will be **written**; staleness outside the scope is reported, never acted on.
   It exits 1 on blocking (a corrupt existing region, or a `--feature` that does not
   exist) -- fix that first. **`--check` stops here** (report drift, write nothing).
3. **Generate (fan out).** For each actionable CREATE/REGENERATE feature, spawn **one
   worker sub-agent** (the brief is `references/subagent-brief.md`). Each worker is given
   that feature's requirements (and any `make-arch` component names) and returns **Mermaid
   text only** -- it writes no files. Assemble the results into one JSON payload:

   ```json
   {"features": {"checkout": {"flows": [
     {"id": "DF-CHK-01", "kind": "data", "covers": ["FR-CHK-001","IR-CHK-001"],
      "title": "Place order", "mermaid": "sequenceDiagram\n  ..."},
     {"id": "UF-CHK-01", "kind": "user", "covers": ["FR-CHK-001"],
      "mermaid": "flowchart TD\n  ..."}
   ]}}}
   ```

4. **Embed (deterministic).** `python scripts/embed_flows.py docs/specs payload.json`.
   It rewrites only the managed region, preserves the frontmatter byte-for-byte and the
   human narrative outside the region (defensive asserts abort the edit if a human moved
   the markers), and is **byte-identical on a no-op** (an unchanged re-run reuses the old
   timestamp, so there is no git diff).
5. **Validate.** `python scripts/validate_flows.py docs/specs [--feature <slug>]...`.
   Fix every FAIL before presenting. Coverage and staleness are warnings (flows are
   advisory); malformed markers, bad Mermaid, a broken stamp, or a disturbed frontmatter
   fingerprint (DF-006) fail.
6. **Report.** An honest receipt: which features got flows, which were SKIP, any
   out-of-scope staleness, and any coverage warnings. Say **PARTIAL** on a scoped run.
   The git diff of the feature files is the archive -- there is no separate changelog.

## Validation rules (`validate_flows.py`, prefix DF-)

- **DF-001** markers well-formed and exactly-once per feature (fail).
- **DF-002** each flow's Mermaid is fenced, non-empty, a known kind, and its id matches
  the grammar `DF-<PREFIX>-NN` (data) / `UF-<PREFIX>-NN` (user) (fail).
- **DF-003** the stamp parses, has the required keys, and `flow_count` matches the blocks
  (fail).
- **DF-004** every `covers=` id resolves to a real requirement, and every active FR is
  covered by a flow (warn -- advisory).
- **DF-005** the stamped `feature_version` differs from the live one -> stale (warn).
- **DF-006** the feature's `meta.fingerprint` still matches a recompute -- the embed did
  not disturb the frontmatter contract (fail-closed; the strong recompute runs when
  `make-spec` is installed alongside, else a structural check).

## Honest limits

- **Flows are advisory.** They do not gate the pipeline and are only as fresh as the last
  run; re-run after a feature's requirements change (DF-005 surfaces staleness).
- **The Mermaid is authored by a sub-agent, not derived.** A diagram is a model's best
  reading of the requirements, not a proof; a human reviews the PR diff like any spec.
- **Scope bounds writes, not detection.** A scoped run reports staleness everywhere but
  writes only the selected features, and says so (PARTIAL).

## Writing rules

Plain words, short sentences, no marketing language. Keep each diagram legible -- one flow
per concern, not a wall of nodes; split a sprawling feature into multiple named flows.
Never use an em dash; use a spaced double hyphen ` -- ` for asides.
