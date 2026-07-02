# Council: The documentation doctrine (intent/state axis, pace layering, and the four additions)

- **Date:** 2026-07-01
- **Type:** artifact review (with a path-selection matrix on the four additions)
- **Status:** proposed

## The question

Should the agency adopt the proposed documentation doctrine -- an intent/state placement axis
("write what can't be derived, derive what can't be trusted to hands, machine-check the seam"),
pace-layered structure by half-life, unit-of-change granularity, repo-canonical storage with
generated projections -- as the governing frame for the docs pipeline, and are the four proposed
additions (glossary, verification-strategy, operations/runbook, architecture-as-projection) the
right next investments?

Disclosure: the doctrine was drafted in the same session that convened this council. Briefs were
stripped of persuasive framing and presented as claims to refute.

## Premise check

The Oracle accepted the premise conditionally: doctrine is genuinely warranted for an agency --
dispersing teams and machine consumers make schema uniformity non-optional -- but found the axis
itself incomplete. State/intent omits **commitment**: the signed, owed, frozen-by-design truth that
fixed-bid economics settle on. The tell: proposed addition (b), the verification layer, is that
missing category smuggling itself back in as a feature request. Also flagged: undefined
load-bearing terms ("derivable", "rot", "unit of change"), no declared domain of validity (when a
small project may opt out), and an untested empirical claim justifying the glossary.

## Convened

Full core of eleven: Oracle (premise), Harbinger, Adversary, Zealot, Scribe, Reckoner, Witness,
Confessor, Sentinel, Architect, Hierophant. All positions collected blind, as isolated sub-agents.
Two anonymized cross-examination agents, one carrying the anti-consensus mandate.

## Positions

- **Oracle** -- premise holds conditionally; axis missing COMMITMENT; (b) is the leak and goes first.
- **Harbinger** -- gates die by insincere compliance: rubber-stamped fingerprints certify stale docs that agents then build at machine speed.
- **Adversary** -- adoption economics inverted for an agency; (d) refuted by the doctrine's own axiom; pilot against a null alternative before adopting.
- **Zealot** -- adopt: the fingerprinted boundary converts rot into a detectable fail-closed build error and is what makes autonomous build agents economically viable.
- **Scribe** -- load-bearing terms undefined; the signed EARS requirement is unclassifiable by the axis; fingerprints check change, not classification.
- **Reckoner** -- holds only as amortized agency infrastructure; generated docs freeze at handoff; (c) is the only addition with a clean billing line; (d) deepens the pipeline that dies when the last billable hour is logged.
- **Witness** *(no veto, narrowly)* -- the client is a counterparty, not an audience: read-only projections sever the redline channel; the runbook's tacit half (the Monday-cron symptom, "call Dana") must be mandated hand-written.
- **Confessor** -- every mechanism hardens the agency's evidentiary position; if the fingerprint regime and generation pipeline do not transfer at handoff, "single source of truth" is a hostage.
- **Sentinel** -- fingerprints authenticate content, not authorship; specs are program input to obedient agents; hostile text laundered in via ingested client material is effectively remote code execution by prompt.
- **Architect** -- C3 breaks on cross-cutting concerns (fan-out across N feature files); the true one-way door is the ID+fingerprint referencing schema; (d) derives a state view from intent, rendering confident lies for half-implemented decisions.
- **Hierophant** -- C2/C5 organize by an author-side property (half-life) instead of reader tasks; (d) produces the vacuous-generated-intent failure C1 itself names; (c) is the pipeline's only missing "doing-mode" artifact.

## Convergence

1. **The axis is incomplete; the repair is concrete.** Replace "two kinds of truth" with **rule +
   regime**: derivability decides who writes (hand vs machine); a **mutability regime** decides how
   it changes -- live / append-only / regenerated / **frozen-at-signature**. The pipeline already
   runs the first three; commitment demands the fourth. Tacit operational knowledge is not a third
   truth-kind (it is hand-written intent) but a real authoring-incentive defect of (c).
2. **The gate certifies less than the doctrine claims** -- three independent holes: not
   classification (Scribe), not sincerity (Harbinger, narrowed to hand-written attestation gates),
   not provenance (Sentinel, narrowed to ingestion laundering). State the gate's honest guarantee;
   treat client-supplied discovery material as untrusted input; add identity-bearing attestations.
3. **The counterparty problem is a C4 defect.** For the commitment layer C4 inverts: the signed
   instrument is legally canonical and the repo copy is the projection. C4 needs a signable frozen
   projection with a defined redline-return channel.
4. **The generator must transfer at handoff** (Confessor's repair answers Reckoner's freeze-rot):
   the pipeline itself becomes a contractual handoff deliverable, or single-source-of-truth is
   lock-in.
5. **C3 softens to a default heuristic** -- cross-cutting concerns get namespaced spec files; the
   real lock-in surface is the ID+fingerprint schema every tool couples to.
6. **Build-time economics survive.** Agents consume the docs inside the fixed bid, so the agency
   captures the machine-consumability payoff intra-project; only the post-handoff half of the
   economic objection stands, and #4 answers it.

## Strongest dissent

The anti-consensus examiner showed the nine-seat pile-on against (d) was **a mob: three mutually
incompatible diagnoses** (derives state from intent / generates intent / hand-written state in
machine costume) converging on one verdict. The repair was hiding in the Oracle's own principle --
*the axis cuts through documents, not between them*: split architecture.md into a hand-written
narrative preamble and a machine-regenerated facts appendix (component inventory, decision-status
table with accepted-vs-implemented metadata), separately gated. (d)-as-specified is dead;
(d)-repaired belongs on the roadmap. Also preserved: the Zealot's narrowed claim -- machine-
verifiable freshness pays during the build via in-project agents -- which defeats the full
economic inversion; and the Adversary's pilot-against-a-null-alternative as method.

## The blind spot

**The pipeline's own generated OpenAPI contract is a generated-normative artifact -- derivable, yet
consumed as a commitment -- which C1 cannot classify.** The counterexample proving the axis broken
was already shipping in the pipeline's inventory; no seat saw it. Second-order blind spots: the room
attacked the fingerprint gate three ways and then kept relying on it; every verdict on (d) assumed
generated means human-free (a generated-draft, human-owned narrative was never examined); and ten
of eleven seats declared HIGH confidence atop terms the Scribe had shown were undefined -- social
convergence masquerading as analysis.

## Tradeoff matrix

| | Original proposal | Council verdict | Required form | Sequence |
|---|---|---|---|---|
| (b) verification | addition #2, a layer | **The repair of C1 -- goes first** | Per-requirement `verification:` field inside the feature spec (not a standalone layer); negative/abuse cases mandated | 1 |
| (a) glossary | addition #1, "cheap" | Right, but redesigned and empirically gated | In-context surfacing at point of use (standalone glossaries go unvisited); fingerprint-scoped -- a pinned term is the highest-degree node in the reference graph, so price invalidation fan-out, not authoring; named owner; test the churn claim against existing CHANGELOGs first | 2 |
| (c) runbook | addition #3 | Right -- but a sub-pipeline, cost it honestly | Accrues during the build; hand-written tacit half mandated; hard machine/hand seam; no-secrets rule + handoff redaction pass; billable line + owner | 3 |
| (d) arch-as-projection | addition #4 | As specified: rejected. Repaired: roadmap | Split document (hand-written narrative + regenerated facts appendix); ADR status metadata (accepted vs implemented); generator ships as a handoff deliverable | 4 |

## Verdict

- **Recommendation:** Adopt the doctrine **amended**: repair the axis to rule + regime (derivability
  decides who writes; mutability regime -- live / append-only / regenerated / frozen-at-signature --
  decides how it changes); add the counterparty workflow to C4; make the generator a handoff
  deliverable; name the gate's honest guarantee and treat ingested client material as untrusted;
  declare a domain of validity; resequence the additions (b) -> (a) -> (c) -> (d)-repaired.
- **Confidence:** medium -- the direction survived eleven blind seats and two cross-examinations,
  but the doctrine's load-bearing terms are undefined and its one empirical claim unmeasured; high
  confidence would repeat the council's own convergence error.
- **First step:** Spec addition (b) as a per-requirement `verification:` field in make-spec's schema
  (with mandated negative/abuse-case entries) -- it is the repair of C1, not addition four-of-four --
  and in the same pass run the CHANGELOG churn analysis that gates the glossary.
