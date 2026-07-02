---
name: make-spec
description: Generate and amend layered project specs for agency work -- a lean project overview plus one churn-friendly spec per feature, with EARS acceptance criteria, pinned/namespaced requirement IDs, content-derived versions, and a validator. Use this skill whenever the user wants to start a spec from discovery material (RFPs, briefs, workshop transcripts, FigJam exports, notes), add or change a feature, write or update requirements, or maintain the spec CHANGELOG. Trigger it for "spec out the project", "requirements doc", "what are we building", "add a feature", or "change this requirement" -- if the deliverable is the spec set or a change to it, this skill applies. The architecture/decisions layer is the downstream make-arch skill; do NOT use this for ADRs or stack choices.
---

# Make a Spec

Build and maintain the layered spec set that is the single source of truth for
**what** an agency project delivers and **why**. The spec lives in `docs/product/`
as a few small documents that read in a sitting, not one monolith:

```
docs/product/
  overview.md            # the lean PRD: problem, users, goals, scope + no-gos,
                         #   the FEATURE INDEX
  features/<slug>.md     # one lean spec per feature (WHAT-only, user stories +
                         #   EARS acceptance)
  CHANGELOG.md           # Keep a Changelog ledger of every change
```

**One file per document.** Each spec is a single Markdown file: the YAML
**frontmatter is the machine-readable contract** (meta + requirements / feature
index) that the validator parses, the fingerprint hashes, and the downstream
skills consume; the **body is human narrative** for reviewers. There is no
separately derived `*-data.yaml` -- the bytes a human reviews and signs ARE the
bytes the pipeline validates and builds from. The frontmatter is authored by
hand and parsed deterministically; only `meta.fingerprint` and
`meta.feature_version` are machine-stamped. (This closes the integrity gap in the
older two-file design, where an LLM re-derived a second copy the human never
signed and the gate only checked that copy against itself.) The architecture
layer (`architecture.md` + `decisions/ADR-*.md`) is produced by the separate
**`make-arch`** skill and referenced from here by ADR id -- this skill never
decides HOW.

**The doctrine: a spec states WHAT and WHY, never HOW.** "The client runs Shopify
Plus" is a constraint and stays; "use the Shopify REST API" is an architecture
decision -- leave a `governed_by` placeholder and let `/make-arch` record the ADR.
When in doubt, reframe as a constraint or defer it to an ADR.

**And every requirement states its proof.** Acceptance criteria say what must be
TRUE (EARS); each requirement's `verification` list says how that will be PROVEN
-- method + check, with at least one negative-path entry per FR (S-014/S-015,
mirroring the required `IF ... THEN` criterion). This is the commitment made
operational: the spec a client signs carries not just the promise but the test
of the promise, and it is the checklist do-work's acceptance gate verifies
against. See `references/verification-methods.md`. A cross-cutting concern
(auth, theming, analytics) that would repeat in every feature gets its own
namespaced feature file instead of fanning out.

## Modes

Decide which one applies before doing anything else:

- **Kickoff** (greenfield) -- no spec exists. Input is a corpus of discovery
  material; output is the first `docs/product/` set. Read `references/kickoff.md`.
- **Amend** (brownfield) -- a spec exists. Input is a change trigger. Output is an
  in-place edit plus a structured `CHANGELOG.md` entry. **Diff, never rewrite.**
  Read `references/amend-and-changelog.md`.

And two flags that compose with the modes:

- **`--lite`** -- for known-small projects (a brochure site, a one-feature tool).
  Produce the overview + feature specs only and skip the architecture layer until
  a real architectural decision arises. Rigor is **opt-out**: the full model is the
  default; `--lite` is the deliberate minimization.
- **`--trivial`** -- a typo or wording fix that changes no ID's *meaning*. Records
  the edit in the CHANGELOG without a full re-stamp/reconcile round-trip. The
  validator's fingerprint gate enforces honesty: if the edit actually changed
  meaning (the fingerprint moved), it is not trivial -- reclassify. See
  `references/amend-and-changelog.md` §2.

## Files in this skill

- `assets/overview-template.md` -- the overview (lean PRD) template. HTML comments
  are authoring instructions; follow them, then strip them.
- `assets/feature-template.md` -- the per-feature template (WHAT-only, EARS).
- `assets/changelog-entry-template.md` -- the structured CHANGELOG entry; its
  Added/Modified/Removed id lists are what `make-issues` reconciles against.
- `assets/spec-data-schema.yaml` -- the schema for both frontmatter shapes, the
  fingerprint **IN/OUT contract**, and validator rules S-001..S-015. Read before
  authoring any spec.
- `references/kickoff.md` -- greenfield: scope the corpus, consolidate the
  overview, distill features, author + stamp + validate.
- `references/amend-and-changelog.md` -- brownfield: classify, diff-don't-rewrite,
  supersede-not-delete, the CHANGELOG delta, the `--trivial` lane.
- `references/ears-grammar.md` -- the five EARS templates the validator parses.
- `references/verification-methods.md` -- the five verification methods
  (test/demo/inspection/analysis/monitor), the per-FR negative-path mandate, and
  the 1.0 -> 1.1 migration lane.
- `references/id-grammar.md` -- the pinned, feature-namespaced ID grammars and the
  traceability chains.
- `scripts/stamp_fingerprint.py` -- run after authoring or editing any spec:
  stamps each fingerprint + content version into the frontmatter (the body is
  preserved) and syncs the Feature Index.
- `scripts/validate_spec.py` -- run after every stamp. Never present a spec whose
  validation fails.

## Location & filing

The canonical home is **`docs/product/`**. The live files always keep their names --
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
  you re-stamp; a priority tweak does not. We claim it **detects and
  blocks internal drift**, never that drift is impossible.
- **No-vanishing against `origin/main`.** The validator diffs IDs against the
  `origin/main` baseline and **fails closed** when that baseline can't be trusted --
  no git repo, a shallow clone, or an unresolvable ref. Fix the git state rather
  than silencing it; `--no-baseline` is only for the greenfield first commit before
  `main` carries the docs.

## The author -> stamp -> validate loop (both modes)

1. Author or edit the single Markdown file -- the structured contract in the
   frontmatter (per the schema), the human narrative in the body. The template
   comments are the rules. There is no separate data file to derive. Set each
   feature's `supports: [G-NNN]` to the overview goal(s) it advances (the
   feature -> objective link the validator resolves and make-trace maps), and
   each requirement's `verification` (how it will be proven -- FRs need a
   negative-path entry). When amending a feature that predates verification
   (schema_version "1.0"), bump it to "1.1" and author the verification then --
   the validator warns until you do and fails closed once bumped.
2. `python scripts/stamp_fingerprint.py docs/product` -- stamps the fingerprint and
   content version into each frontmatter (your body is preserved) and syncs the
   Feature Index.
3. `python scripts/validate_spec.py docs/product` (add `--no-baseline` only on the
   greenfield first commit). Fix every failure before presenting; if a fix means
   downgrading an unsourced claim to an open question, say so in your report.

For a large corpus, push the bulky, self-contained work to sub-agents -- one reader
per source returns a cited digest; consolidation, ID assignment, and the
stamp/validate loop stay coordinated centrally (see `references/kickoff.md`).

## Honest limits

State what the spec does not yet settle, plainly, rather than papering over it:
goals without a baseline, requirements whose failure path was inferred rather than
stated, decisions deferred to an ADR, claims that rest on a weak source. A kickoff
with visible open questions is healthy; a spec that hides its gaps is not. Never
invent a source, a metric, or a behavior to make the validator pass.

And be honest about what the gate proves: a fingerprint certifies that **these
bytes have not changed since they were stamped** -- nothing more. It does not
prove the content is correctly classified, that a human actually re-read it
before re-stamping, or who authored the change (git carries authorship). The
gate detects and blocks drift; correctness is verification's job, and sincerity
is the reviewer's.

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
