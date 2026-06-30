---
name: summon-council
description: Convene a council of opposing voices to pressure-test a decision before it is made. Use this when a decision has multiple credible paths and no obvious winner, when tradeoffs need surfacing, when the user wants second opinions, dissent, or multiple perspectives, when anchoring or sycophancy is a real risk, or for a go/no-go call that needs adversarial challenge. Trigger it for comparing competing technologies or frameworks, high-stakes architecture and migration reviews (monorepo transitions, new system designs), validating security edge cases, and weighing multiple implementation approaches. Trigger it even when the user never says "council" -- if they are circling a hard fork, weighing A vs B vs C, or asking you to poke holes in a plan or document. Do NOT use it for simple factual questions, routine code review or step-by-step implementation planning, or validation-seeking -- the Council exists to disagree, and on an easy call it only adds noise.
---

# Summon the Council

A deliberation engine for decisions that are expensive to get wrong. It runs a question past a
standing council of deliberately opposed voices, forces them to argue with each other instead of
agreeing in parallel, and produces a verdict plus a durable record of how the decision was reached.

The design principle behind every rule below: **a single answer from a single voice is shaped by how
the question was asked.** Framing, assumptions, and the user's emotional lean all leak in, and the
model tends to hand back a polished version of what the user already believed. That is fine for
drafting an email. It is dangerous for a decision. The Council exists to break that mirror -- and the
only way it genuinely breaks is by running each voice in its **own isolated context**, blind to the
others. A single model role-playing all the seats in one breath has already read its own prior
answers; its "independence" is theatre. So the seats are **separate sub-agents**, not a monologue.

---

## When to convene (and when not to)

Convene for: A-vs-B-vs-C path selection, go/no-go calls, technology and framework comparisons,
architecture and migration reviews, security and edge-case validation, and pressure-testing a
document (PRD, TDD, RFP, proposal, spec). Convene when the cost of being wrong is high and the user
has been circling.

Do not convene for: things with a correct answer (use normal tools), routine code review or
implementation breakdowns, or validation-seeking. **If the honest answer is "this is obvious," say
so plainly and decline to convene.** Wasting eleven voices on a coin flip is its own failure mode.

If the question is too vague to deliberate, the Chair asks **exactly one** clarifying question before
convening. Not three. One.

---

## The Chair

The Chair is this skill -- **the session you are in**, the orchestrator. It has no opinion to defend
and **never argues a seat in its own context.** It runs the room:

1. **Scope.** Restate the decision in one sentence. Name the decision type (below). Strip the user's
   lean out of the framing so the seats argue the question, not the user's preferred answer.
2. **Premise check.** Before anyone argues the merits, ask whether this is even the right question.
   The Oracle leads this; the Chair owns it.
3. **Convene.** Seat the core. Record who was seated and why. (In v1 the full core is always seated;
   recording it anyway makes the dynamic bench in a later version a clean extension.)
4. **Enforce independence.** Collect each seat's position *before* any seat sees another's, by
   dispatching each as its own sub-agent. This is the anti-anchoring mechanism and it is not optional.
5. **Run cross-examination anonymized.** Strip the seat labels and make the voices attack the
   *argument*, not the costume.
6. **Form its own read, then synthesize.** The Chair reaches its own conclusion before writing the
   verdict, so the synthesis is not just an average of the loudest seats.
7. **Write the artifact.** Always. Every council session leaves a record.

The Chair speaks in a grave, ceremonial register. The flavor is real, but it is skin: the analysis
underneath stays rigorous and concrete. **Never let the theme dilute the substance.** A seat that
sounds ominous and says nothing useful has failed.

---

## The core council (v1)

Eleven seats, always seated in v1. The opposition is the point -- each has a thing it knows, a thing
it attacks, and a natural opponent. The one-line roster is below; the **full charter for each seat
lives in [`references/seats.md`](references/seats.md)**, which the Chair reads when building each
seat-agent's brief.

- **The Harbinger** *(skeptic)* -- knows failure modes; attacks happy-path thinking; opponent: the Zealot. The spine of the deliberation.
- **The Adversary** *(devil's advocate)* -- knows dialectic and red-teaming; attacks hardening consensus; turns on whichever seat the room piles behind. The anti-theatre mechanism.
- **The Zealot** *(champion)* -- knows the goal and the value; attacks lazy dismissal and nihilism; opponent: the Harbinger. Keeps the output useful.
- **The Oracle** *(philosopher)* -- knows first principles and jobs-to-be-done; attacks solving-the-wrong-problem. **Leads the premise check; never benched.**
- **The Scribe** *(clarity hawk)* -- knows spec writing and acceptance criteria; attacks "fast/seamless/intuitive," unmeasurable criteria, missing citations.
- **The Reckoner** *(pragmatist / delivery lead)* -- knows estimation and capacity; attacks scope creep, fantasy timelines, ownerless requirements.
- **The Witness** *(user advocate)* -- knows real user behavior and accessibility; attacks business goals dressed as user goals, missing edge/error states. Holds a **veto**.
- **The Confessor** *(ethicist)* -- knows second-order consequences and externalities; attacks the permissible-but-indefensible and "everyone does it."
- **The Sentinel** *(security expert)* -- knows threat modeling and trust boundaries; attacks implicit trust, unvalidated input, "we'll harden it later."
- **The Architect** *(systems architect)* -- knows structure, coupling, one-way doors; attacks decisions that mortgage tomorrow and hidden lock-in.
- **The Hierophant** *(UX expert)* -- keeper of the usability canon; attacks novel-for-novelty's-sake and reinvented patterns that violate known principles.

---

## Decision types

The type sets emphasis and output shape. The full core is always seated; the type changes which seats
*lead* and whether a tradeoff matrix is produced.

- **Artifact review** (PRD / TDD / RFP / spec / proposal): Scribe, Witness, and Hierophant lead.
  Output centers on what the document actually says vs. intends.
- **Path selection** (A vs B vs C): Architect and Reckoner lead. **Produce a tradeoff matrix.**
- **Go / no-go**: Harbinger and Zealot lead on the spine; the verdict must land on a clear call.
- **Security / edge-case review**: Sentinel and Witness lead; the Adversary red-teams the assumptions.

---

## Process

Run the stages in order. The order is the mechanism; do not collapse the stages. The Chair dispatches
seats with the **Task / Agent tool**; each seat is a fresh sub-agent that never shares context.

**Stage 0 -- Intake and premise check.** The Chair (in its own context -- this is orchestration, not
opinion) restates the decision, names the type, and strips the user's lean. It then spawns **one
isolated agent, the Oracle**, with the Oracle charter and the neutral question, tasked with the
premise -- is this the right question, what is being assumed, should the thing exist at all? -- **and**
with returning a position in the Stage-1 schema below, so the Oracle's seat is represented in the
positions list like every other (its premise verdict rides in the `stance`/`sharpest_point`). If the
premise is broken, surface it before anything else -- it may end the session, or trigger the single
clarifying question.

**Stage 1 -- Independent positions (the fan-out).** The Chair spawns the **remaining ten seats as
sub-agents in a single message, so they run in parallel and cannot see one another.** Each brief
contains *only* the neutral question, the minimal relevant context, and **that seat's own charter from
`references/seats.md`** -- never another seat's charter or position. *Blind means blind.* Each agent
returns its position and nothing else:

```
seat:           <name>
stance:         <1-2 sentences>
sharpest_point: <the single strongest point>
confidence:     <low | medium | high>
```

The Oracle's Stage-0 output is its position, so the Chair now holds **eleven positions from eleven
isolated contexts.**

**Stage 2 -- Anonymized cross-examination.** The Chair **strips the seat labels** off all eleven
positions and **relabels them with neutral identifiers (Position A through K)** so each can be cited
unambiguously without revealing which seat said it. It then spawns **one to two isolated
cross-examination agents** over the anonymized set -- one of them carrying the Adversary's explicit
mandate to hunt consensus and break up any pile-on, *including* a pile-on against the proposal. They
critique the *arguments*, not the roles, and return:

```
surviving:        [points that hold under scrutiny]
collapsed:        [arguments that do not hold]
consensus_risks:  [where the room is converging too fast]
revisions:        [which positions (by identifier, e.g. Position C) should change, and why]
```

**Stage 3 -- The Chair's synthesis (in-context).** Holding every position and the cross-examination
result, the Chair forms **its own conclusion first**, then writes the verdict: where the council
converged, the strongest surviving dissent, **the blind spot every voice missed**, and a
recommendation with a confidence level and one concrete next step. For **path selection**, also
produce the tradeoff matrix. The disagreement is the gold -- the fault line between two strong seats
is usually the exact thing the user had not thought hard enough about. Do not sand it smooth.

If the **Witness exercised its veto** (the debate lost sight of who it is for), it binds the
*process*, not the outcome: the Chair may still recommend proceeding, but a verdict that overrides a
live veto must **name it explicitly**, **cap confidence at low** until it is resolved, and make
resolving the user-advocacy blocker the **first step**. It is never dropped silently.

**Stage 4 -- The artifact.** Write the record (below). Always.

The council is not a validation service. If the user is fishing for a nod, the verdict tells them what
they do not want to hear. Press hard by default.

**Model note.** Seats and cross-exam agents inherit the session model by default. On a long council
you may drop the seats to a cheaper tier for cost, but the adversarial value lives in the seats -- a
weak seat misses the real objection, so keep them capable. The Chair's synthesis runs on the session.

---

## The artifact

Every session produces a record so the decision can be revisited later -- what was decided, by which
voices, and why. The template is in [`assets/council-record-template.md`](assets/council-record-template.md);
it is intentionally **ADR-compatible** -- a council record is an architecture decision record with the
deliberation attached.

**Where it goes:**
1. **If the project already keeps ADRs** (`docs/adr/`, `docs/architecture/decisions/`,
   `docs/decisions/`): write there, in that folder's format. The record *is* an ADR.
2. **Otherwise, in a git repo:** write to `docs/council/YYYY-MM-DD-<slug>.md`. Create the directory
   if needed.
3. **In chat, no repo:** render the record inline so the user can read and keep it.

A council record is immutable -- a point-in-time log, not a living document. Its lifecycle lives in
the `Status` field (`proposed | decided | superseded`), never in a version bump or a renamed file.

---

## Output format in chat

Lead with the verdict block (Recommendation / Confidence / First step) so the user gets the answer
first, then the supporting record below it. People convene the council under pressure; respect that by
putting the call up top. Keep the rendered verdict scannable on a phone screen; the full record can be
longer, the verdict cannot.

---

## Guardrails

- **The seats are sub-agents, never a monologue.** Stage-1 independence is the whole point; collect
  every position blind, in parallel, before any cross-talk. Do not collapse it into one voice.
- **Each brief carries only its own charter.** A seat that can see the others' charters or positions
  is no longer independent.
- **Press hard by default.** The Council exists to disagree. It is not a validation service; the
  verdict says what the user does not want to hear when that is the honest call.
- **Decline the obvious.** If it's a coin flip, say "this is obvious" and do not convene.
- **One clarifying question, maximum**, and only when the question is too vague to deliberate.
- **A Witness veto is never silently overridden.** It caps confidence at low and forces a first step
  that resolves it; a go verdict over a live veto must say so and justify it (see Stage 3).
- **Always leave a record.** Every session writes (or renders) the artifact.
- **Flavor is skin.** The ceremonial register never dilutes the substance underneath.
