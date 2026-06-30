# Recommend-then-Refine (with confidence as typed data)

How make-arch proposes an architecture without pretending to certainty it does not
have. The principle, praised in the design roast and protected here: **recommend a
concrete stack, but type every choice's confidence so a human refines against the
right things.**

## The loop

1. **Read the inputs.** The overview (problem, goals, constraints, scope) and every
   feature spec. The architecture exists to cover those features -- nothing more.
2. **Recommend a concrete stack.** Do not hedge into a menu. Pick components,
   integrations, and the decisions behind them. A real recommendation a human can
   react to beats five balanced options.
3. **Type the confidence of each choice** (this is the discipline):
   - **`known`** -- backed by a stated requirement, a constraint, or a client fact.
     *Cite it.* "Client runs Shopify Plus (CON-003)" -> the commerce platform is
     `known`.
   - **`assumption`** -- a sensible default you are supplying because the inputs are
     silent. "No stated search load, so a managed Postgres FTS is enough for now" ->
     `assumption`. State what would confirm or overturn it.
   Confidence is **typed data** in `arch-data.yaml` (`confidence: known | assumption`),
   not a tone in prose. The validator requires it on every component, integration,
   and decision (A-005).
4. **Surface the assumptions as a badge.** In `architecture.md`, mark
   assumption-backed choices visibly (a `**assumption**` badge). This is the point
   where a human architects deliberately -- they scan the badges, confirm or
   redirect, and the next run promotes confirmed assumptions to `known`.
5. **Record each real decision as an ADR** (see `adr-protocol.md`). The architecture
   overview names and links them; the ADR holds the Context / Decision /
   Consequences / rejected alternatives.

## Why typed confidence, not just good prose

A reviewer skimming an architecture doc cannot tell a load-bearing fact from a
plausible default unless you mark it. Typing the confidence turns "is this settled?"
into a field a human can filter on and a tool can count -- the validator reports how
many assumption-backed choices remain, so an architecture full of unconfirmed
defaults cannot quietly read as finished.

## Honest limits

If the inputs genuinely do not determine a choice, say so and pick the reversible
default -- an `assumption` ADR you can supersede cheaply later -- rather than
inventing a requirement to justify a hard-to-reverse one. Never fabricate a
constraint to upgrade an assumption to `known`. The whole value of the confidence
field is that it is truthful.
