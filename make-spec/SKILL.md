---
name: make-spec
description: Generate and amend layered project specs for agency work -- a lean project overview plus one churn-friendly spec per feature, with EARS acceptance criteria, pinned/namespaced requirement IDs, content-derived versions, and a validator. Use this skill whenever the user wants to start a spec from discovery material (RFPs, briefs, workshop transcripts, FigJam exports, notes), add or change a feature, write or update requirements, or maintain the spec CHANGELOG. Trigger it for "spec out the project", "requirements doc", "what are we building", "add a feature", or "change this requirement" -- if the deliverable is the spec set or a change to it, this skill applies. The architecture/decisions layer is the downstream make-arch skill; do NOT use this for ADRs or stack choices.
---

# Make a Spec

Build and maintain the layered spec set that is the single source of truth for
**what** an agency project delivers and **why**. The spec lives in `docs/specs/`
as a few small documents that read in a sitting, not one monolith:

```
docs/specs/
  overview.md  / overview-data.yaml      # the lean PRD: problem, users, goals,
                                          #   scope + no-gos, the FEATURE INDEX
  features/<slug>.md / <slug>-data.yaml   # one lean spec per feature (WHAT-only,
                                          #   user stories + EARS acceptance)
  CHANGELOG.md                            # Keep a Changelog ledger of every change
```

Each layer is **Markdown that people read and sign** plus a derived `*-data.yaml`
that downstream tools consume. The Markdown wins every disagreement; the YAML is
regenerated and re-stamped, never hand-edited. The architecture layer
(`architecture.md` + `decisions/ADR-*.md`) is produced by the separate
**`make-arch`** skill and referenced from here by ADR id -- this skill never
decides HOW.

**The doctrine: a spec states WHAT and WHY, never HOW.** "The client runs Shopify
Plus" is a constraint and stays; "use the Shopify REST API" is an architecture
decision -- leave a `governed_by` placeholder and let `/make-arch` record the ADR.
When in doubt, reframe as a constraint or defer it to an ADR.

## Modes

Decide which one applies before doing anything else:

- **Kickoff** (greenfield) -- no spec exists. Input is a corpus of discovery
  material; output is the first `docs/specs/` set. Read `references/kickoff.md`.
- **Amend** (brownfield) -- a spec exists. Input is a change trigger. Output is an
  in-place edit plus a structured `CHANGELOG.md` entry. **Diff, never rewrite.**
  Read `references/amend-and-changelog.md`.

And two flags that compose with the modes:

- **`--lite`** -- for known-small projects (a brochure site, a one-feature tool).
  Produce the overview + feature specs only and skip the architecture layer until
  a real architectural decision arises. Rigor is **opt-out**: the full model is the
  default; `--lite` is the deliberate minimization.
- **`--trivial`** -- a typo or wording fix that changes no ID's *meaning*. Records
  the edit in the CHANGELOG without a full re-derive/reconcile round-trip. The
  validator's fingerprint gate enforces honesty: if the edit actually changed
  meaning (the fingerprint moved), it is not trivial -- reclassify. See
  `references/amend-and-changelog.md` §2.

## Files in this skill

- `assets/overview-template.md` -- the overview (lean PRD) template. HTML comments
  are authoring instructions; follow them, then strip them.
- `assets/feature-template.md` -- the per-feature template (WHAT-only, EARS).
- `assets/changelog-entry-template.md` -- the structured CHANGELOG entry; its
  Added/Modified/Removed id lists are what `make-issues` reconciles against.
- `assets/spec-data-schema.yaml` -- the schema for both data-file shapes, the
  fingerprint **IN/OUT contract**, and validator rules S-001..S-012. Read before
  deriving any YAML.
- `references/kickoff.md` -- greenfield: scope the corpus, consolidate the
  overview, distill features, derive + validate.
- `references/amend-and-changelog.md` -- brownfield: classify, diff-don't-rewrite,
  supersede-not-delete, the CHANGELOG delta, the `--trivial` lane.
- `references/ears-grammar.md` -- the five EARS templates the validator parses.
- `references/id-grammar.md` -- the pinned, feature-namespaced ID grammars and the
  traceability chains.
- `scripts/stamp_fingerprint.py` -- run after deriving any data file: stamps each
  fingerprint + content version and syncs the Feature Index.
- `scripts/validate_spec.py` -- run after every stamp. Never present a spec whose
  data file fails validation.

## Location & filing

The canonical home is **`docs/specs/`**. The live files always keep their names --
the version lives in the data (the per-feature content version and the overview
`project_version`), never in the filename. **Git history is the archive**; a PR
diff is the change proposal. There is no `archive/`/`changes/` folder -- to see a
prior version, read it from git.

## Versioning, the fingerprint gate, and no-vanishing

- **Content-derived versions.** Each feature's `feature_version` is the first 12
  hex of its content fingerprint -- derived from the spec, with no counter to race.
  The overview Feature Index mirrors it.
- **The fingerprint is a fail-closed gate, not a notification.** It is computed
  over the **contract** content only (acceptance criteria, descriptions,
  `governed_by`, `depends_on`, interface -- the IN set), excluding advisory fields
  (priority, hints, notes -- the OUT set). The validator refuses to pass when a
  stored fingerprint ≠ its recompute. So a change of *meaning* blocks the run until
  you re-derive and re-stamp; a priority tweak does not. We claim it **detects and
  blocks internal drift**, never that drift is impossible.
- **No-vanishing against `origin/main`.** The validator diffs IDs against the
  `origin/main` baseline and **fails closed** when that baseline can't be trusted --
  no git repo, a shallow clone, or an unresolvable ref. Fix the git state rather
  than silencing it; `--no-baseline` is only for the greenfield first commit before
  `main` carries the docs.

## The derive -> stamp -> validate loop (both modes)

1. Author/edit the Markdown (the template comments are the rules).
2. Derive the affected `*-data.yaml` per the schema.
3. `python scripts/stamp_fingerprint.py docs/specs`
4. `python scripts/validate_spec.py docs/specs` (add `--no-baseline` only on the
   greenfield first commit). Fix every failure before presenting; if a fix means
   downgrading an unsourced claim to an open question, say so in your report.

For a large corpus, push the bulky, self-contained work to sub-agents -- one reader
per source returns a cited digest; consolidation, ID assignment, and the
derive/validate loop stay coordinated centrally (see `references/kickoff.md`).

## Honest limits

State what the spec does not yet settle, plainly, rather than papering over it:
goals without a baseline, requirements whose failure path was inferred rather than
stated, decisions deferred to an ADR, claims that rest on a weak source. A kickoff
with visible open questions is healthy; a spec that hides its gaps is not. Never
invent a source, a metric, or a behavior to make the validator pass.

## Downstream

`/make-arch` reads the overview + features and produces `architecture.md` + the ADR
log (skip it for `--lite`). `/make-issues` reads the spec set + the CHANGELOG delta
and reconciles GitHub issues. `/do-work` builds from those issues. Change flows
forward: amend here -> re-run the downstream lanes; never edit scope inside an issue.

## Writing rules

Plain words, short sentences, no marketing language. Requirements use one behavior
at a time. Never use an em dash; use a spaced double hyphen ` -- ` for asides. Write
so a reader outside the project -- or an AI issue generator -- can act on each item
without asking what it means.
