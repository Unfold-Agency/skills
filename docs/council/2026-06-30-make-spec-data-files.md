# Council: Does make-spec need derived YAML data files?

- **Date:** 2026-06-30
- **Type:** path selection
- **Status:** proposed

## The question
For an AI-agent-driven specs pipeline (`make-spec → make-arch → make-issues → do-work`), should the
structured machine layer be a separately-derived, schema-validated, fingerprinted `*-data.yaml` per
document (A), markdown-only as the single core data (B), or a single markdown file whose structured
data lives in frontmatter/fenced blocks that the validator parses directly (C)?

## Premise check
The Oracle rejected "YAML vs Markdown" as the framing. The real question is **what machine-checkable
invariants an LLM-driven pipeline must guarantee, and by what authority** — file format is downstream
of that. Its load-bearing reframe: the `*-data.yaml` is **not** a deterministic derivation. An LLM
(not a compiler) emits it, so the fingerprint hashes *the YAML's own fields* and verifies the YAML's
**self-consistency**, never its fidelity to the Markdown a human actually signed.

## Convened
All eleven core seats (v1 seats the full bench). Architect and Reckoner led (path selection). The
Witness spoke for the humans in the loop and the room moved *with* that interest, so no veto was
triggered. Two anonymized cross-examiners ran over the relabeled positions; the second performed
code-level forensics on `validate_spec.py`, `item_fingerprint.py`, `stamp_fingerprint.py`, and the
make-issues reconciliation docs.

## Positions
- **Oracle:** wrong frame; fingerprint verifies YAML-vs-itself, not YAML-vs-signed-Markdown → C.
- **Harbinger:** A fails loudly, B/C silently; agent silently re-scopes a req on re-derive and the
  gate passes against the new wrong YAML; C least-bad but only if frontmatter isn't regenerated and
  the human actually reviews it → C (caveated).
- **Adversary:** B is the seductive trap — it scatters parsing into every downstream agent and removes
  the only fail-closed gate; the fingerprint is the load-bearing organ; real fight is A vs C.
- **Zealot:** the structured layer is what makes four LLM stages shippable; prose can't carry the
  fingerprint gate; keep A's value, deliver as C.
- **Scribe:** "Markdown wins disagreements" is an unenforceable rule, not a mechanism; content written
  twice; the gate hashes the copy, not the signed original → C.
- **Reckoner:** the derived file is sync overhead a solo agency can't own; keep the schema check +
  per-requirement fingerprint, drop the re-derivation → C.
- **Witness:** A betrays the three humans — author signs Markdown, build runs from an LLM-derived YAML
  they never read; manufactured false accountability → C.
- **Confessor:** A is indefensible on client work; the gate verifies the YAML against itself =
  manufactured attestation; only C builds from the bytes the human signed.
- **Sentinel:** the fingerprint gate is theatre — the same untrusted LLM derives the YAML *and*
  re-stamps the hash, and it hashes the wrong artifact; a real binding needs a deterministic
  (non-agent) hash over the signed artifact, gated behind a human signature.
- **Architect:** load-bearing decision is *where signed truth lives vs. where the inter-stage contract
  lives*; prose can't be the contract for LLM stages (kills B); A's drift is a one-way door; C unifies
  and is reversible.
- **Hierophant:** A violates DRY/single-source-of-truth/convention; **verified that the validator
  parses only the YAML and reads the `.md` solely to count words** — the canon (frontmatter/fenced
  blocks, as SKILL.md itself uses) already solves this → C.

## Convergence
Near-unanimous. Ten of eleven seats recommended **C**; the eleventh (Adversary) named the real fight
as A-vs-C, not whether structure should exist. **B is dead** as the pipeline is shaped today — it
loses the stable-ID + per-requirement-fingerprint anchor make-issues needs and reintroduces
non-deterministic prose-parsing at every downstream stage.

## Strongest dissent
The pro-**A** steelman that *no seat made during the blind round*, surfaced only by adversarial
cross-examination: a sidecar keeps the human-signed, client-facing prose **clean** and **visibly
marks the structured layer as machine output to be treated as suspect.** Inlining deeply-nested
per-requirement YAML (EARS arrays, dependency graphs, `interface` sketches) into the signed document
risks an unreviewable wall *and* **launders** LLM output into the human-signed artifact. This bounds
the verdict: C only wins if the structured block stays genuinely reviewable and the human is actually
expected to review it.

## The blind spot
**The Markdown is not a superset of the machine contract — verified in code.** In the test fixtures,
`interface: 'order: { id, items, amount, status }'` exists **only** in `checkout-data.yaml`; it is
absent from `checkout.md`. `interface` is an IN field — it is hashed into the fingerprint and embedded
into generated issues. `depends_on` lives as English prose ("Depends on FR-CART-001."), not a
machine-extractable list. So the human signs a Markdown that is **missing hashed contract fields the
build actually consumes.** No seat checked this. It dissolves *both* the naive-B claim ("prose is
enough") and the naive-C claim ("signed bytes == built bytes") at once: the defect is not "two files,"
it is **"the signed file omits fields that drive the build, and the gate hashes a copy the human never
saw."** Worse, `validate_spec.py`'s S-006 failure message claims the data file "drifted from its
markdown" — but the check has no access to the markdown's content. The gate's own message describes a
fidelity check the code does not perform.

## Tradeoff matrix

| Axis | A: derived sidecar YAML (status quo) | B: markdown-only | C: one file, structured frontmatter |
|---|---|---|---|
| Stable IDs across stages | ✅ (in YAML) | ✅ (headings, regex-extractable) | ✅ (in frontmatter) |
| Change-detection scoped to one issue | ✅ via IN/OUT-projected per-req fingerprint | ❌ naive prose hash churns on cosmetic edits | ✅ **iff** it keeps the IN/OUT projection |
| No-vanishing-IDs vs git baseline | ✅ (scans `*-data.yaml`) | ⚠️ possible over headings | ⚠️ needs baseline scan repointed |
| Fidelity of contract to *signed* intent | ❌ hashes unsigned YAML | ❌ no hash | ❌ naive: hashes LLM-regenerated block |
| Single source of truth / DRY | ❌ two copies, LLM-synced | ✅ | ✅ |
| Human-signed == machine-consumed bytes | ❌ | ✅ (but prose lacks `interface`) | ✅ **iff** structured block reviewed |
| Keeps signed prose clean / review-light | ✅ (separation of concerns) | ✅ | ⚠️ risk of unreviewable wall |
| `--trivial` / advisory-churn safety | ✅ (OUT set stripped before hash) | ❌ | ✅ iff IN/OUT projection preserved |
| Maintenance / token cost per run | ❌ re-derive + re-stamp a 2nd file | ✅ | ✅ (one artifact; validator survives) |
| Migration cost from today | — (none) | high | high (rewrites 4 skills + reconciler) |
| Reversibility | one-way drift accrual | prose-parse lock-in | A→C / B→C reversible |

**Decisive row: "Fidelity of contract to signed intent" is delivered by NONE of A/B/C as described.**
It requires deterministic extraction + the human reviewing (or the prose carrying) every hashed field
— a control **orthogonal to file count.** The C-consensus mistook a layout change for the fidelity fix.

## Verdict
- **Recommendation:** Don't frame this as "keep or kill the YAML." **Fix the fidelity gap first — it
  is the real defect, and it is independent of the file question.** (1) Make the signed artifact a
  *true superset* of the hashed contract: every IN field (notably `interface`, and a structured
  `depends_on`) must appear in what the human reviews — or stop hashing fields the human can't see.
  (2) Compute the fingerprint **deterministically over the signed bytes**, not as an LLM re-stamp of
  an LLM-derived copy. Once those two controls exist, A-vs-C is mostly cosmetic — and on the merits
  (DRY, one signature, no two-copy sync drift, convention) **C edges it**, *provided* the structured
  block stays genuinely reviewable. If per-requirement structure is too heavy to inline cleanly, a
  sidecar that is deterministically derived and explicitly *not* the source-of-record is still
  defensible. The keystone is **one deterministic hash over what the human actually signed**, not the
  number of files.
- **Confidence:** **High** on the diagnosis (the fidelity gap, the hash-the-wrong-artifact gate, and
  the Markdown-isn't-a-superset finding are all verified in code). **Medium** on "C over A" — the
  inlining-readability cost and a four-skill-plus-reconciler migration are real and were not costed,
  and the highest-value fix doesn't require choosing C at all.
- **First step:** Add `interface` and a structured `depends_on` to the feature Markdown template so
  every hashed IN field is present in the artifact the human signs; then either point
  `compute_fingerprint` at that signed region or add the missing Markdown-vs-data fidelity check
  (`validate_spec.py` currently has none, despite S-006's message claiming it). Do this **before** any
  decision to collapse to a single file.
