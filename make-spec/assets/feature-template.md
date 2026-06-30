<!--
═══════════════════════════════════════════════════════════════════
FEATURE TEMPLATE -- docs/specs/features/<slug>.md   (make-spec)

The lean, churn-heavy layer: one feature, WHAT-only. User stories +
EARS acceptance criteria + appetite/no-gos. The governing technical
decision is referenced by id in the derived data file's `governed_by`
(an ADR-NNNN from make-arch) -- it is NOT restated here. "Use Stripe"
is an ADR; "the system shall capture payment" is a requirement here.

KEEP IT LEAN. A feature spec should be reviewable in one sitting. The
validator WARNS (S-012) above the budget (~12 requirements / ~1200
words). If a feature is bigger than that, split it into two features.

IDs. Every requirement is <kind>-<PREFIX>-<NNN>:
  FR  functional   IR  integration   NFR  non-functional   CR  content
<PREFIX> is this feature's uppercased short slug from the Feature Index
(e.g. CHK for checkout) and must match for every id in this file
(S-007). IDs are never reused or renumbered; a cut requirement becomes
status: superseded or deferred, never deleted (S-005).

Strip all HTML comments before publishing. Never an em dash; use ` -- `.
═══════════════════════════════════════════════════════════════════
-->

---
doc_type: spec-feature
slug: ""                  # kebab-case; matches the file name + index row
prefix: ""                # ^[A-Z]{2,5}$ ; the requirement namespace
title: ""
status: active            # active | superseded | deferred
appetite: ""              # Shape Up budget, e.g. "2 weeks" (optional)
data_file: features/<slug>-data.yaml
---

# [Title]

**Story.**
<!-- One or more user stories: As a <role>, I want <capability>, so that
<benefit>. The narrative spine the requirements below serve. -->

**No-gos.**
<!-- Shape Up no-gos: what is explicitly out of bounds for THIS feature,
so the appetite holds. -->

---

## FR-<PREFIX>-001 -- [short name]

<!-- One behavior. The description states WHAT, plainly. -->
[Description.]

**Acceptance criteria** (EARS -- see references/ears-grammar.md):
- The system shall [response].                                  <!-- ubiquitous -->
- WHEN [trigger], the system shall [response].                  <!-- event-driven -->
- IF [unwanted condition], THEN the system shall [response].    <!-- unwanted (REQUIRED for every FR -- the failure path, S-011) -->

**Depends on:** <!-- other requirement IDs, or none -->
**Governed by:** <!-- ADR-NNNN if an architecture decision governs this; else none -->
**Interface:** <!-- data shape / contract sketch, when useful -->
**Priority:** must <!-- must | should | could | wont -- advisory, OUT of the fingerprint -->

<!-- Repeat the block per requirement. Integration (IR), non-functional
(NFR), and content (CR) requirements use the same shape; only FRs are
required to carry an unwanted-behavior (IF...THEN) criterion. -->
