<!--
═══════════════════════════════════════════════════════════════════
OVERVIEW TEMPLATE -- docs/specs/overview.md   (make-spec)

The lean PRD layer: the slow-changing project context every feature
shares. Problem, users, goals + metrics, scope + no-gos, and the
FEATURE INDEX. It states WHAT and WHY at the project level; it does
NOT enumerate per-feature requirements (those live in features/<slug>.md)
and it does NOT decide HOW (that is an ADR, via make-arch).

Everything in HTML comments is authoring guidance and MUST be stripped
from the published overview. Plain words, short sentences, no marketing
language. Never an em dash; use a spaced double hyphen ` -- ` for asides.

TWO FILES, ONE TRUTH. This Markdown is what people read and sign. The
Skill derives overview-data.yaml from it and stamps a fingerprint; the
YAML is generated, never hand-edited. scripts/validate_spec.py fails the
run if they drift.
═══════════════════════════════════════════════════════════════════
-->

---
doc_type: spec-overview
project_id: ""            # e.g. proj-2026-014
project_name: ""
client: ""
project_version: "0.1"    # a human milestone label, not a lock -- the
                          # real change signal is each feature's content
                          # version (see the Feature Index)
mode: full                # full | lite (lite skips the architecture layer)
status: draft             # draft | review | approved
last_updated: ""          # YYYY-MM-DD
data_file: overview-data.yaml
---

# [Project Name] -- Spec Overview

## Problem

<!-- One short paragraph: the problem we are solving and why now. Plain
words. This is the "why" the whole spec set serves. -->

## Users

<!-- Who this is for and what they are trying to do. One row per
audience -- summarize, link decks, do not paste them. -->

| Audience | Description | Primary needs |
|---|---|---|
| | | |

## Goals & Success Metrics

<!-- Every goal needs a MEASURABLE metric and how/when it is measured.
"User-friendly" is not a metric. If a baseline is unknown, leave it
blank and say so in prose -- never invent a number. IDs are G-001, G-002,
... and never reused. -->

| ID | Kind | Goal | Metric | Measurement method | Baseline |
|---|---|---|---|---|---|
| G-001 | business / user | | | | |

## Scope

### In scope
<!-- Short feature-area lines. Each becomes (or maps to) a feature spec. -->

### Out of scope (parking lot)
<!-- What stakeholders raised that we are NOT doing, with a reason and a
disposition (future-phase / declined / needs-pricing). This protects the
budget. -->

| Item | Reason | Disposition |
|---|---|---|
| | | |

### Non-goals
<!-- Outcomes we are explicitly NOT chasing, even if adjacent. Distinct
from out-of-scope features -- these are outcomes. -->

## Feature Index

<!-- THE REGISTRY. Every features/<slug>.md MUST appear here. The Skill
maintains feature_version (the content-derived version of each feature
spec) and the prefix (the uppercased short slug that namespaces that
feature's requirement IDs, e.g. CHK for checkout). Prefixes are unique
across the project. The validator (S-007/S-008) enforces all of this. -->

| Slug | Prefix | Title | Version | Status | Appetite |
|---|---|---|---|---|---|
| checkout | CHK | | | active | 2 weeks |

<!--
═══════════════════════════════════════════════════════════════════
CHECKLIST -- strip before publishing
□ Every goal has a measurable metric + a measurement method (S-009)
□ Every feature file has a Feature Index row; prefixes are unique
□ Out of scope captures everything raised but cut
□ overview-data.yaml derived, fingerprint stamped, validator passes
□ All guidance comments removed
═══════════════════════════════════════════════════════════════════
-->
