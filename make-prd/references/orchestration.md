# Sub-Agent Orchestration (Large Corpora)

How to keep a large engagement inside one working context without drowning in raw material. Read this when the corpus is too big to hold and reason over at once, or before the YAML derivation step in either mode. For a small corpus (a couple of short documents) skip it and work inline -- fanning out a tiny corpus costs more than it saves.

The prime directive: **push the bulky, self-contained work to sub-agents; keep the work that needs a whole-document view in the main context.** Reading raw transcripts and running the YAML derive/validate/fix loop are bulky and self-contained. Extraction is not -- it needs one mind across every section and source.

## 1. When to fan out

Fan out when any of:

- More than ~3 substantial sources
- Any transcript longer than ~30 minutes
- Total intake larger than you can comfortably hold while still reasoning over it

Otherwise read everything inline.

## 2. Reading: one sub-agent per source (parallel)

After the Source Index is confirmed (`corpus-intake.md`), dispatch one reader sub-agent per source, or per small group of like sources. They run in parallel. Each reader's job is to read one source and return a compact, cited digest -- not to write requirements.

Give each reader:

- The source (or its link) and its handle from the index
- The template's section list, so the digest is organized the way extraction expects
- The citation rules: every candidate item carries handle + locator; weak sources get weak locators; never invent

Each reader returns a digest containing only:

- **Candidate items**, grouped by template area (objectives, scope, FRs, constraints, ...), each a one-line statement with its locator (e.g. `WS-1 @ 00:34:12`)
- **Conflicts or tensions** noticed within that source
- **Gaps** the source gestures at but does not answer

No IDs, no acceptance criteria, no prose -- those are assigned centrally. The digests, not the raw sources, return to the main context. That is what keeps hour-long transcripts out of the working window.

## 3. Extraction stays central

Do **not** fan out extraction itself. One agent -- the main context -- assembles the digests and runs the extraction pass from `extraction-guide.md`:

- IDs are assigned once, globally unique. Parallel agents would collide.
- `depends_on`, `supports`, and conflict detection span sections and sources. Only a whole-corpus view sees them.
- Routing (no source → KU, "how" → constraint or TDD, conflict → Section 13) needs one consistent hand.

Reader agents surface; the central agent decides. This preserves every integrity rule the validator later checks.

## 4. Deriving and validating the YAML (one sub-agent)

The derive → validate → fix loop is mechanical and verbose, and the same in both modes. Once the Markdown is final, hand it to one sub-agent rather than running it inline. Give the sub-agent:

- The finalized PRD Markdown (master + shards)
- `assets/prd-data-schema.yaml` and `scripts/validate_prd.py`
- In Amend mode, the prior `prd-data.yaml` for `--prev`

The sub-agent:

1. Derives `prd-data.yaml` per the schema.
2. Runs the validator (`--prd-md`, plus `--prev` in Amend mode).
3. Fixes failures -- downgrading unsourced items to Known Unknowns where the guide requires, never inventing sources to pass.
4. Returns the validated YAML and the standard report: counts per section, open KUs, open conflicts, and anything it downgraded.

It returns only once the validator exits 0. Never present a PRD whose data file fails validation -- that rule holds whether the loop ran inline or in a sub-agent.
