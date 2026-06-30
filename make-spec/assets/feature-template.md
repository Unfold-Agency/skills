<!--
═══════════════════════════════════════════════════════════════════
FEATURE TEMPLATE -- docs/specs/features/<slug>.md   (make-spec)

ONE FILE, ONE TRUTH. The YAML frontmatter is the machine-readable
contract -- it is what the validator parses, what the fingerprint
hashes, and what make-issues/make-arch/do-work consume. The body below
is human narrative for reviewers. There is NO separate data file: the
bytes you review and sign ARE the bytes the pipeline trusts. The body
must not introduce contract claims (requirements, criteria, deps) that
are not in the frontmatter.

The lean, churn-heavy layer: one feature, WHAT-only. User stories +
EARS acceptance criteria + appetite/no-gos. The governing technical
decision is referenced by id in each requirement's `governed_by` (an
ADR-NNNN from make-arch) -- it is NOT restated here. "Use Stripe" is an
ADR; "the system shall capture payment" is a requirement here.

KEEP IT LEAN. A feature spec should be reviewable in one sitting. The
validator WARNS (S-012) above the budget (~12 requirements / ~1200
words). If a feature is bigger than that, split it into two features.

IDs. Every requirement is <kind>-<PREFIX>-<NNN>:
  FR  functional   IR  integration   NFR  non-functional   CR  content
<PREFIX> is this feature's uppercased short slug from the Feature Index
(e.g. CHK for checkout) and must match for every id in this file
(S-007). IDs are never reused or renumbered; a cut requirement becomes
status: superseded or deferred, never deleted (S-005).

meta.fingerprint and meta.feature_version are STAMPED by the Skill
(scripts/stamp_fingerprint.py) -- leave them blank when authoring, never
hand-edit. Strip all HTML comments before publishing. Never an em dash;
use ` -- `.
═══════════════════════════════════════════════════════════════════
-->

---
meta:
  doc_type: spec-feature
  schema_version: "1.0"
  slug: ""                  # kebab-case; matches the file name + index row
  prefix: ""                # ^[A-Z]{2,5}$ ; the requirement namespace
  title: ""
  status: active            # active | superseded | deferred
  appetite: ""              # Shape Up budget, e.g. "2 weeks" (optional) -- OUT of the fingerprint
  feature_version: ""       # STAMPED -- first 12 hex of the fingerprint
  fingerprint: ""           # STAMPED -- sha256 over contract content
user_stories:
  - "As a <role>, I want <capability>, so that <benefit>."
no_gos: []                  # Shape Up no-gos: explicit out-of-bounds for THIS feature
requirements:
  - id: "FR-<PREFIX>-001"
    name: "<short name>"
    kind: functional        # functional | integration | nonfunctional | content
    description: ""          # WHAT, one behavior, plainly -- IN the fingerprint
    acceptance_criteria:     # EARS (see references/ears-grammar.md) -- IN the fingerprint
      - "The system shall <response>."                                  # ubiquitous
      - "WHEN <trigger>, the system shall <response>."                  # event-driven
      - "IF <unwanted condition>, THEN the system shall <response>."    # unwanted -- REQUIRED for every FR (S-011)
    governed_by: []          # ADR-NNNN ids if an architecture decision governs this -- IN the fingerprint
    depends_on: []           # other requirement ids (within or across features) -- IN the fingerprint
    interface: ""            # data shape / contract sketch, when useful -- IN the fingerprint
    # ── advisory; OUT of the fingerprint (change freely, no re-stamp) ──
    priority: must           # must | should | could | wont
    architecture_hints: ""
    related_files: []
    notes: ""
    status: active
---

# [Title]

<!-- HUMAN NARRATIVE. The frontmatter above is the signed contract; this body
helps a reviewer understand it. Summarize and reference requirements by id; do
not restate acceptance criteria here (they live, authoritatively, above). -->

**Story.** [Restate the user story/stories in prose.]

**No-gos.** [What is explicitly out of bounds for this feature, so the appetite holds.]

[A short paragraph: how the requirements hang together, the seams to other
features (by id), and any context a reviewer needs. Reference requirements like
`FR-<PREFIX>-001`; the contract itself is the frontmatter.]
