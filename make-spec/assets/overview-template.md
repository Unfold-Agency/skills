<!--
═══════════════════════════════════════════════════════════════════
OVERVIEW TEMPLATE -- docs/specs/overview.md   (make-spec)

ONE FILE, ONE TRUTH. The YAML frontmatter is the machine-readable
contract (problem, users, goals/metrics, scope + no-gos, and the
FEATURE INDEX). The body below is human narrative for reviewers. There
is NO separate data file -- the bytes you review and sign ARE the bytes
the pipeline validates and hashes.

The lean PRD layer: the slow-changing project context every feature
shares. It states WHAT and WHY at the project level; it does NOT
enumerate per-feature requirements (those live in features/<slug>.md)
and it does NOT decide HOW (that is an ADR, via make-arch).

meta.fingerprint is STAMPED by scripts/stamp_fingerprint.py; the
feature_index feature_version values are stamped too (mirrored from each
feature). Leave them blank when authoring; never hand-edit. Plain words,
short sentences, no marketing language. Never an em dash; use ` -- `.
Strip all HTML comments before publishing.
═══════════════════════════════════════════════════════════════════
-->

---
meta:
  doc_type: spec-overview
  schema_version: "1.0"
  project_id: ""            # e.g. proj-2026-014
  project_name: ""
  client: ""
  project_version: "0.1"    # a human milestone label, not a lock -- OUT of the fingerprint
  mode: full                # full | lite (lite skips the architecture layer)
  status: draft             # draft | review | approved
  fingerprint: ""           # STAMPED -- sha256 over contract content
problem: ""                 # one or two sentences: the problem and why now
users:
  - name: ""
    description: ""
    primary_needs: []
goals:
  - id: "G-001"
    kind: business          # business | user
    statement: ""
    metric: ""              # the measurable success criterion (S-009)
    measurement_method: ""  # how/when measured -- required (S-009)
    baseline: ""            # "" allowed; note the gap in the body, never invent
    status: active
scope:
  in_scope: []              # short feature-area lines
  out_of_scope:             # the parking lot -- what we are NOT doing
    - item: ""
      reason: ""
      disposition: future-phase   # future-phase | declined | needs-pricing
non_goals: []               # outcomes we are explicitly NOT chasing
feature_index:              # THE REGISTRY -- every features/<slug>.md MUST have a row
  - slug: ""                # kebab-case; the file is features/<slug>.md
    prefix: ""              # ^[A-Z]{2,5}$ -- unique across the project (S-003/S-007)
    title: ""
    feature_version: ""     # STAMPED -- mirrors the feature's content version (S-008)
    status: active          # active | superseded | deferred
    appetite: ""            # OUT of the fingerprint
---

# [Project Name] -- Spec Overview

<!-- HUMAN NARRATIVE. The frontmatter above is the signed contract; this body
helps a reviewer read it. Summarize; do not invent metrics or restate the index
as a second source of truth. -->

## Problem

[One short paragraph: the problem we are solving and why now.]

## Users

[Who this is for and what they are trying to do. Summarize; link decks, do not
paste them.]

## Goals

[Each goal G-NNN with its measurable metric and measurement method. If a
baseline is unknown, say so plainly -- never invent a number.]

## Scope

[In-scope feature areas; the out-of-scope parking lot with dispositions; the
non-goals (outcomes we are not chasing).]

## Feature Index

[A readable table of the features (slug, prefix, title, appetite). The
authoritative index -- including each feature's stamped version -- is the
frontmatter.]

<!--
═══════════════════════════════════════════════════════════════════
CHECKLIST -- strip before publishing
□ Every goal has a measurable metric + a measurement method (S-009)
□ Every feature file has a Feature Index row; prefixes are unique
□ Out of scope captures everything raised but cut
□ Fingerprints stamped (scripts/stamp_fingerprint.py); validator passes
□ All guidance comments removed
═══════════════════════════════════════════════════════════════════
-->
