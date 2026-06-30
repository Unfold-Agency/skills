# Kickoff (greenfield first pass)

How to turn disparate client inputs -- RFPs, briefs, workshop transcripts, FigJam
exports, stakeholder notes -- into the first `docs/specs/` set: an `overview.md`,
a lean spec per feature, and a seeded `CHANGELOG.md`. Read this when no spec exists
yet. Amend mode (a spec already exists) is `amend-and-changelog.md`.

## 1. Scope the corpus, then inventory it

The prime directive: **gather within a named scope the user confirms -- never
across the whole account.** A spec cites its sources; a corpus vacuumed from
everywhere can't be cited honestly and risks dragging another client's data in.

- If the user hasn't handed you the full corpus, ask for a named scope first: a
  project/engagement name, a client, a Drive folder, an email thread, a date range.
- Pull only what the scope names. Map each input to a short, stable handle (`RFP`,
  `BRIEF`, `WS-1` workshop, `MTG-1` meeting, `FJ-1` FigJam, `INT-name` interview,
  `EM-1` email, `AN-1` analytics) and capture its link.
- Assemble everything into a draft source list and **confirm it with the user
  before extracting**. This is a gate. Items they exclude are dropped; items they
  add get a handle.
- Assess citation strength as you log each source. A transcript without
  timestamps, an unlabeled notes file, gets a weaker locator -- never an invented
  one. Claims resting only on a too-weak source become open questions, not
  requirements.

For a large corpus (more than ~3 substantial sources, or any long transcript),
fan out: one reader sub-agent per source returns a compact, cited digest; the raw
transcripts stay out of the main context. **Consolidation and extraction stay
central** -- IDs, cross-references, and conflict detection need one mind across the
whole corpus.

## 2. Consolidate into the overview

Fill `assets/overview-template.md`. The overview is the slow-changing project
context every feature shares:

- **Problem / Users** -- the why, plainly. Summarize and link decks; don't paste.
- **Goals & metrics** -- every goal `G-NNN` needs a measurable metric and a
  measurement method (S-009). Unknown baseline -> leave blank and say so; never
  invent a number.
- **Scope** -- in-scope feature areas, an out-of-scope parking lot with
  dispositions, and non-goals (outcomes we are not chasing).
- **Feature Index** -- list each feature you are about to write, with a unique
  **prefix** (the uppercased short slug, e.g. `CHK`). The Skill fills
  `feature_version` later, at stamp time.

## 3. Distill the feature set

Each in-scope area becomes one `features/<slug>.md` from `assets/feature-template.md`.
Keep each lean (the validator warns above ~12 requirements / ~1200 words -- split a
feature that overflows). For each feature:

1. **User stories + no-gos** -- the narrative spine and the appetite's guardrails.
2. **Requirements**, one behavior each, WHAT-only. Route as you go:
   - No source supports it -> it's an open question, not a requirement (note it in
     prose; do not invent). This is the anti-hallucination rule.
   - It dictates HOW (a vendor, an API, a datastore) -> that's an ADR (make-arch),
     not a requirement. Leave a `governed_by` placeholder if a decision is needed;
     don't bake the decision into the spec.
   - It's two behaviors -> split into two requirements.
3. **IDs** -- `<kind>-<PREFIX>-<NNN>` using the feature's prefix (see
   `id-grammar.md`).
4. **Acceptance criteria in EARS** (see `ears-grammar.md`). Force at least one
   unwanted-behavior (`IF ... THEN ...`) criterion on every FR -- the failure path.
5. **Priority** is advisory (`must`/`should`/`could`/`wont`) and OUT of the
   fingerprint; set it, but don't agonize -- it can change without a re-sync.

## 4. Question pass

Before deriving, sweep for gaps and ask the user the highest-value questions (cap
around 7): goals without a measurable metric, FRs with no responsibly-inferable
failure path, an unnamed decision-maker, unstated content ownership, implied-but-
unconfirmed constraints. Everything else is noted as an open item. Ship the first
pass with honest gaps -- do not block on answers.

## 5. Author, stamp, validate

1. Author `overview.md` and each `features/<slug>.md` from the templates -- one
   file each, the structured contract in the **frontmatter** (per
   `assets/spec-data-schema.yaml`), the human narrative in the body. There is no
   separate data file to derive.
2. Stamp the fingerprints: `python scripts/stamp_fingerprint.py docs/specs`. This
   hashes each spec's frontmatter and writes each feature's content version into
   the overview Feature Index (it rewrites only the frontmatter; bodies are kept).
3. Validate. On a brand-new repo with no pushed `main` yet, the no-vanishing
   baseline doesn't exist, so pass `--no-baseline`:
   ```
   python scripts/validate_spec.py docs/specs --no-baseline
   ```
   Once `main` carries the docs, drop the flag (the default baseline is
   `origin/main`). Never present a spec whose validator fails -- fix or downgrade
   items until it passes, and tell the user what you downgraded.
4. Seed `CHANGELOG.md` with a single `kickoff` entry (see
   `assets/changelog-entry-template.md`): the IDs created, grouped under Added.

## 6. Hand off

Report: features created, requirement counts per feature, goals and their metrics,
open questions, and anything routed somewhere the user might not expect (a "how"
deferred to an ADR, an unsourced claim demoted to a question). The next lane is the
architecture: `/make-arch` reads the overview + features and proposes the stack as
`architecture.md` + an ADR log. `--lite` projects skip that and go straight to
`/make-issues`.
