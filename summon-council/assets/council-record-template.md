<!--
Council record template -- intentionally ADR-compatible. A council record is an architecture
decision record with the deliberation attached. If the project already keeps ADRs, write into that
folder and follow its format instead; otherwise write to docs/council/YYYY-MM-DD-<slug>.md.

The record is immutable: a point-in-time log, not a living document. Lifecycle lives in the Status
field (proposed | decided | superseded), never a version bump or a renamed file. Keep the Verdict
block scannable on a phone; the rest of the record may run longer. Delete this comment in the output.
-->

# Council: <decision title>

- **Date:** <YYYY-MM-DD>
- **Type:** <artifact review | path selection | go-no-go | security review>
- **Status:** <proposed | decided | superseded>

## The question
<one-sentence decision, with the user's lean stripped out>

## Premise check
<did the Oracle accept the question, or reframe it? what was assumed?>

## Convened
<the Oracle (premise gate), the core trio (always seated), which bench seats were summoned and why, and which were benched>

## Positions
<terse, one line per seat -- the position and its sharpest point>

## Convergence
<where the council agreed>

## Strongest dissent
<the most important disagreement that survived cross-examination>

## The blind spot
<what every voice missed until it was forced into the open>

## Tradeoff matrix
<path-selection only: options as columns, decision axes as rows>

## Verdict
- **Recommendation:** <the call>
- **Confidence:** <low | medium | high, with one line of why>
- **First step:** <one concrete action, not "it depends">
