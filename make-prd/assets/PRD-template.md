<!--
═══════════════════════════════════════════════════════════════════
MASTER PRD TEMPLATE — v1.1
Mondo Robot / RFEF Lane 2 (Requirement Formalization)

HOW THIS TEMPLATE WORKS
- This file is both a human template and the instruction set for the
  PRD-generation Skill. Everything inside HTML comments is guidance
  for the author (human or AI) and MUST be stripped from the final PRD.
- The PRD answers WHAT we are building and WHY, in detail.
  It does not answer HOW. Architecture, staffing, roles, and delivery
  approach belong in the TDD. If you find yourself writing "use
  PostgreSQL" or "the React app will...", move it to the TDD or
  reframe it as a constraint (see Section 8).
- Every requirement, constraint, assumption, and open question gets
  a stable ID. IDs are never reused or renumbered, even when items
  are cut. Cut items move to Out of Scope or get status: superseded.
  Downstream lanes (models, tickets, designs, UAT scripts) reference
  these IDs, so breaking them breaks traceability.
- Every extracted item gets a SOURCE. The Skill must cite where each
  requirement came from (transcript timestamp, doc name + section,
  interview + speaker). No source = goes to Section 11 (Open
  Questions) as unverified, not into Requirements.
- If sources conflict, do NOT pick a winner silently. Log it in
  Section 13 (Conflicts & Decisions) and flag for human resolution.

THE PRD IS A LIVING DOCUMENT
- The PRD changes over the life of the project, but only through the
  Change Management protocol in Section 1. Edits outside that
  protocol don't count and won't propagate.
- Versioning is major.minor. Minor = additive or clarifying (new FR
  within scope, a KU resolved, a source added). Major = the meaning
  of an existing requirement, objective, scope item, or constraint
  changed. Anything design or engineering discovers downstream that
  forces a major bump must route back here BEFORE tickets change.
- Ticket refinement is not PRD change. Design detail, final copy,
  and implementation nuance live on tickets. The test: does the
  change alter any ID'd item in this document? No → refine the
  ticket. Yes → PRD amendment first.

TWO FILES, ONE TRUTH
- This Markdown file is authored by humans (and the Skill) and is
  the document people read, review, and sign.
- The Skill derives a companion machine file, prd-data.yaml, from
  this document on every version bump. The YAML is generated, never
  hand-edited. Its `version` must match this file's frontmatter
  exactly; the validator fails the build if they drift, if any ID is
  malformed/duplicated, if required fields are blank, or if an item
  references an ID that doesn't exist.

SHARDING (LARGE ENGAGEMENTS)
- When Section 7 exceeds ~30 FRs or review becomes unwieldy, shard:
  keep this file as the master index (Sections 1–6, 8–14) and move
  Section 7 detail into docs/07-requirements/[feature-area].md, one
  file per feature area from 6.1. List shards in the frontmatter.
  IDs stay globally unique across shards; the derived YAML is always
  compiled from master + all shards as one logical document.

FILING & ARCHIVING
- The canonical home for the PRD pair in a repo is docs/: the master
  Markdown at docs/PRD-[project].md and the derived docs/prd-data.yaml.
  Shards live under docs/07-requirements/. The live files always keep
  these names -- the version lives in the frontmatter, never the filename.
- On every version bump (amend mode, before applying the diff), snapshot
  the OUTGOING version into docs/archive/ with its version in the name:
  docs/archive/PRD-[project]-v<old>.md and docs/archive/prd-data-v<old>.yaml.
  The archived prior prd-data.yaml is exactly what the validator's --prev
  consumes. Generate mode (v0.1) archives nothing.

ID PREFIXES
  BO-  Business objective        FR-  Functional requirement
  UO-  User objective            CR-  Content requirement
  NFR- Non-functional req        IR-  Integration requirement
  CON- Constraint                AS-  Assumption
  KU-  Known unknown / open Q    DEP- Dependency
  RSK- Risk                      ER-  Environmental/physical req
═══════════════════════════════════════════════════════════════════
-->

---
# Machine-readable document metadata. Keep this block valid YAML.
doc_type: PRD
project_id: ""            # e.g. proj-2026-014
project_name: ""
client: ""
phase: ""                 # set only if the Brief splits the engagement
                          # into phased PRDs; e.g. "phase-1". Blank =
                          # single PRD for the engagement.
version: "0.1"            # major.minor — see Change Management (1.2)
supersedes: ""            # previous version, e.g. "1.3"
status: draft             # draft | review | approved | superseded
last_updated: ""          # YYYY-MM-DD
authors: []
data_file: "docs/prd-data.yaml"   # canonical derived path (generated,
                          # never hand-edited; version must match)
shards: []                # e.g. ["07-requirements/checkout.md"] (relative
                          # to docs/) — empty for single-file PRDs
related_docs:
  brief: ""               # link or path to the Brief
  tdd: ""                 # link or path to the TDD (may not exist yet)
  rfp: ""                 # original RFP, if any
source_corpus: []         # list every input the PRD was built from
                          # e.g. "workshop-transcript-2026-05-02.txt"
approvals: []             # filled at sign-off: name, role, date
---

# [Project Name] — Product Requirements Document

## 1. Document Control & Change Management

### 1.1 Version History

| Version | Date | Author | Class | Changed IDs | Summary | Triggered by |
|---|---|---|---|---|---|---|
| 0.1 | | | — | — | Initial draft | Discovery corpus |

<!-- "Triggered by" names the origin of the change: a ticket ID, a
UAT issue, a design finding, a client request. Every row after
approval should trace to something concrete. -->

**Approval required from:** <!-- Names + roles. Pulled from Section 12. -->

**Reading guide:** Sections 2–5 are for everyone. Sections 6–11 are the working spec for design, engineering, and QA. Sections 12–14 are governance.

### 1.2 Change Classes

<!-- The PRD is living, but changes only land through this protocol.
The point: design and build refine TICKETS; only discoveries that
alter the WHAT come back here. -->

| Class | What it covers | Version bump | Downstream effect |
|---|---|---|---|
| Ticket refinement | Design detail, final copy, implementation nuance. Alters no ID'd item in this doc. | none | Update the ticket only |
| Minor amendment | Additive or clarifying: new FR within existing scope, KU resolved, source added, wording clarified without changing meaning | minor (x.Y) | Regenerate prd-data.yaml; generate new tickets if needed; existing tickets untouched |
| Major amendment | Meaning of an existing objective, requirement, scope item, or constraint changes; anything cut or added beyond approved scope | major (X.0) | Requires approval per Section 12 → TDD review → ticket re-evaluation (1.3) |

### 1.3 Propagation on a Major Amendment

<!-- This encodes the loop: build → discovery → PRD → TDD → tickets
→ build. Order matters; skipping steps is how docs and tickets
drift apart. -->

1. The discovery (blocker, UAT issue, client decision) is written up against the affected IDs and logged in Section 13.
2. PRD amended; version bumps major; changed IDs recorded in 1.1; approval obtained per Section 12.
3. prd-data.yaml regenerated; validator confirms version + ID integrity.
4. TDD reviewed against the changed IDs; revised if affected; TDD version recorded.
5. All tickets referencing a changed ID are re-evaluated: updated, closed as superseded, or replaced. New tickets created where needed. Every ticket carries the PRD version it was generated against, so the affected set is a query, not a hunt.
6. Work resumes from the re-evaluated backlog.

### 1.4 Escalation Intake

<!-- The formal on-ramp from build (Lane 6) back to this document.
Full record schema lives in prd-data-schema.yaml (ESC- records). -->

**The rule:** anyone — AI agent or human — who cannot satisfy an acceptance criterion as written, or who finds a missing requirement, ambiguity, or constraint conflict, raises an escalation and pauses that ticket. No patching around it, no reinterpreting it, no silently narrowing it. AI agents may raise and propose; only a named human decides.

**Decision outcomes:** refine-ticket (PRD untouched) · minor amendment (x.Y) · major amendment (X.0 → full propagation per 1.3) · rejected (criterion stands; ticket resumes with guidance). Escalations resulting in amendments are referenced in the Version History "Triggered by" column. Open escalations block approval status.

---

## 2. Summary

<!--
One page max. Write this LAST. A stakeholder who reads nothing else
should walk away knowing: the problem, what we're building, what
success looks like, and the one or two biggest open risks.
No marketing language. Plain words.
-->

**The problem:**

**What we're building:**

**What success looks like:**

**Biggest open items:** <!-- Top 2-3 from Sections 10/11, by impact -->

---

## 3. Background & Context

<!--
Why this project, why now. Pull from the Brief and discovery, don't
restate the whole Brief. Cover: business situation, what prompted
this (the trigger), what exists today (current site/app/process),
prior attempts if relevant. Cite sources.
-->

### 3.1 Why now
### 3.2 Current state
### 3.3 Relationship to the Brief

<!-- One paragraph: what the Brief committed to, and what this PRD
covers within that. If this PRD covers a phase or slice of the Brief,
say so explicitly. -->

---

## 4. Goals & Success Metrics

<!--
Two lists: business objectives and user objectives. Every objective
needs at least one MEASURABLE success criterion plus how and when
we'll measure it. "User-friendly" is not a criterion. If a baseline
is unknown, that's a KU- entry — link it, don't invent a number.
-->

### 4.1 Business Objectives

| ID | Objective | Priority | Success criteria | Measurement method | Baseline | Source |
|---|---|---|---|---|---|---|
| BO-001 | | must / should / could | | | | |

### 4.2 User Objectives

| ID | Objective | Priority | Success criteria | Measurement method | Source |
|---|---|---|---|---|---|
| UO-001 | | | | | |

### 4.3 Non-Goals

<!-- Outcomes we are explicitly NOT chasing, even if adjacent. e.g.
"This project does not aim to increase newsletter signups." Prevents
scope drift via good intentions. Distinct from out-of-scope features
(Section 6.2) — these are outcomes, not features. -->

---

## 5. Audience & Experience

<!--
The experiential heart of the document. Who is this for, what are
they trying to do, and what should it feel like. Personas and
journeys may live in Lane 1/3 artifacts — summarize and LINK rather
than duplicating full decks.
-->

### 5.1 Audiences

| Audience | Description | Primary needs | Source |
|---|---|---|---|

### 5.2 Key Journeys / Jobs-to-be-Done

<!-- The 3-7 journeys that matter. Each: trigger → steps → desired
outcome. These become the spine for FRs, wireflows, and UAT scripts. -->

### 5.3 Experience Principles

<!-- 3-5 qualitative principles that guide design decisions, with a
test for each. e.g. "Fast over fancy — no interaction should make a
user wait for decoration." These are the tie-breakers when
requirements don't settle a design debate. -->

---

## 6. Scope

### 6.1 In Scope

<!--
The feature inventory, grouped by experience area or feature set
(these groupings typically become Epics in Lane 4). One line per
feature; detail lives in Section 7. Each maps to at least one
objective — if it maps to none, question why it's here.
-->

| Feature area | Includes | Supports objectives |
|---|---|---|

### 6.2 Out of Scope (Parking Lot)

<!--
First-class, not an afterthought. Everything stakeholders raised
that we are NOT doing, with the reason and disposition. This list
is what protects the budget. -->

| Item | Reason excluded | Disposition (future phase / declined / needs pricing) | Source |
|---|---|---|---|

### 6.3 Phasing

<!-- Only if multi-phase. Which features land in which phase, and
what the phase boundary criteria are. -->

---

## 7. Requirements

<!--
The contract. Rules for every requirement in this section:
- Stable ID, never renumbered
- Priority: must / should / could / won't (MoSCoW)
- At least one acceptance criterion in Given/When/Then form —
  Lane 4's ticket generator consumes these directly
- Source citation
- States the WHAT. If it dictates implementation, demote it to a
  constraint or move it to the TDD.
- Cover unhappy paths: errors, empty states, loading, permissions.
  If only the happy path is specified, the requirement isn't done.
-->

### 7.1 Functional Requirements

<!-- Repeat this block per requirement. Group under the feature
areas from 6.1. -->

#### FR-001 — [Short name]
- **Feature area:**
- **Priority:** must-have
- **Description:** <!-- "The system must allow a user to..." Plain,
  testable language. One behavior per FR. -->
- **Acceptance criteria:**
  - Given … when … then …
  - Given [failure/edge case] … when … then …
- **Supports:** UO-xxx, BO-xxx
- **Depends on:** <!-- other FR/IR/DEP IDs, or "none" -->
- **Source:** <!-- transcript-2026-05-02 @ 00:34:12; RFP §3.2 -->
- **Notes / open items:** <!-- link KU- IDs if unresolved -->

### 7.2 Content Requirements

<!--
Who writes, supplies, migrates, and approves content. The most
common cause of agency timeline blowouts. Be specific: page counts,
asset formats, languages, migration volumes, CMS authoring needs.
-->

| ID | Requirement | Owner (client/agency) | Volume/format | Priority | Source |
|---|---|---|---|---|---|
| CR-001 | | | | | |

### 7.3 Integration Requirements

<!-- WHAT must connect and what data flows, not how. "Orders must
sync to NetSuite within 5 minutes" is a requirement. "Use the
NetSuite REST API with token auth" is TDD material. -->

| ID | System | What must happen | Data involved | SLA / constraint | Priority | Source |
|---|---|---|---|---|---|---|
| IR-001 | | | | | | |

### 7.4 Non-Functional Requirements

<!--
Defaults below apply to every project unless explicitly waived in
Conflicts & Decisions. Add project-specific NFRs (SEO, localization,
uptime, data retention) as needed. Every NFR needs a verification
method or it's a wish.
-->

| ID | Category | Requirement | Verification method | Derived from | Priority |
|---|---|---|---|---|---|
| NFR-001 | Accessibility | WCAG 2.2 AA conformance | Automated (axe-core) + manual screen reader pass | default | must |
| NFR-002 | Performance | [e.g. LCP < 2.5s at p75 on 4G] | Lighthouse CI / field data | | |
| NFR-003 | Security & privacy | [e.g. consent management, data handling per GDPR/CCPA as applicable] | | | |
| NFR-004 | Analytics & measurement | Events instrumented to verify every success criterion in Section 4 | Tracking plan review | Section 4 | must |
| NFR-005 | Browser/device support | [support matrix] | Cross-browser QA | | |

### 7.5 Environmental & Physical Requirements (optional module)

<!--
Use for IRL work: installations, activations, events, physical
products (e.g. a printed card game). Delete this section for purely
digital projects. Acceptance criteria here are inspection- or
rehearsal-based rather than Given/When/Then — state what gets
verified and how (proof approval, site walkthrough, dry run).
Fabrication methods and vendor choices belong in the TDD.
-->

| ID | Requirement | Type (venue / fabrication / print / staffing-as-experience / logistics) | Verification method | Supports | Priority | Source |
|---|---|---|---|---|---|---|
| ER-001 | | | | | | |

---

## 8. Constraints

<!--
Hard boundaries the solution must live within. Constraints are
facts, not choices — "client's stack is Shopify Plus" is a
constraint; "we should use Shopify" is a TDD decision. Mark whether
each is negotiable.
-->

| ID | Type | Constraint | Negotiable? | Implications | Source |
|---|---|---|---|---|---|
| CON-001 | technical / budget / timeline / brand / legal / organizational | | yes/no | | |

---

## 9. Dependencies

<!--
Things this project needs from outside the team — overwhelmingly
client-side deliverables in agency work. Each gets an owner and a
need-by date. Late dependencies are the #1 schedule killer; this
table is the early-warning system.
-->

| ID | Dependency | Owner | Needed by | Blocks | Status |
|---|---|---|---|---|---|
| DEP-001 | e.g. brand guidelines, final copy, API credentials, legal review | | | FR-xxx | pending |

---

## 10. Assumptions & Risks

### 10.1 Assumptions

<!-- Things we're treating as true without proof. Each needs a risk
level and a validation plan. An assumption nobody plans to validate
is a risk in disguise. -->

| ID | Assumption | Risk if wrong | Validation method | Owner | Source |
|---|---|---|---|---|---|
| AS-001 | | low/med/high | | | |

### 10.2 Risks

<!-- Project-level risks with a mitigation, not a vibe. Keep to
risks that affect WHAT we build or whether objectives are met;
delivery-process risks belong in the TDD. -->

| ID | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| RSK-001 | | | | | |

---

## 11. Known Unknowns / Open Questions

<!--
First-class uncertainty. Every question that blocks or shapes a
requirement, with an owner and a due date. The Skill routes anything
it can't source or resolve here — this section being long in v0.1
is healthy; it being long at approval is not.
-->

| ID | Question | Why it matters (blocks what) | Assigned to | Due | Status |
|---|---|---|---|---|---|
| KU-001 | | | | | open |

---

## 12. Stakeholders & Decision Authority

<!--
Who can approve, who must be consulted, who gets informed. Name the
single decision-maker for scope disputes — "the client" is not a
person. -->

| Name | Role / org | Authority | Sign-off required? |
|---|---|---|---|

**Escalation path for scope disputes:**

---

## 13. Conflicts & Decisions Log

<!--
The audit trail. Every place the source corpus disagreed with
itself, plus the resolution and who made the call. The Skill
populates conflicts; humans populate resolutions. Unresolved
conflicts block approval.
-->

| # | Conflict | Sources in tension | Resolution | Decided by | Date |
|---|---|---|---|---|---|

---

## 14. Glossary

<!-- Project and client-domain terms, defined once. Include client
jargon picked up in discovery — it prevents the same word meaning
two things in tickets later. -->

| Term | Definition |
|---|---|

---

## Appendix A: Source Index

<!--
Inventory of every input document with a short handle used in Source
citations throughout. The Skill generates this first, then cites
against it.
-->

| Handle | Document | Type | Date |
|---|---|---|---|
| WS-1 | workshop-transcript-2026-05-02.txt | transcript | 2026-05-02 |

<!--
═══════════════════════════════════════════════════════════════════
AUTHOR / SKILL CHECKLIST — strip before publishing
□ Every FR has Given/When/Then criteria incl. at least one failure path
□ Every objective has a measurable criterion + measurement method
□ Every item has a source citation, or lives in Section 11
□ No implementation decisions (those moved to TDD or Constraints)
□ Out of Scope captures everything stakeholders raised but we cut
□ All conflicts in Section 13 resolved before status: approved
□ prd-data.yaml regenerated; validator passes; versions match
□ Version history row complete: class, changed IDs, trigger
□ Major amendments: approval recorded, TDD reviewed, affected
  tickets re-evaluated (Section 1.3 fully executed)
□ Shards (if any) listed in frontmatter; IDs unique across shards
□ All guidance comments removed from the published version
═══════════════════════════════════════════════════════════════════
-->