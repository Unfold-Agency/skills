# Extraction Guide (Generate Mode)

How to turn a messy discovery corpus into a sourced, validated PRD draft. Read this after inventorying the corpus, before extracting anything.

## 1. Corpus intake

Build Appendix A (Source Index) first. One row per input document with:

- **Handle**: short, stable, citation-friendly. Conventions: `RFP`, `BRIEF`, `WS-n` (workshop transcripts, numbered by date), `INT-name` (interviews), `MTG-n` (meeting notes), `FJ-n` (FigJam exports), `AN-n` (analytics).
- **Type, date, URI**: Gemini Meet transcripts are usually linked from the Calendar event -- capture that link when available.

Assess each source's citation strength and work with what it has:

| Source type | Best locator | Fallback |
|---|---|---|
| Transcript with timestamps | `WS-1 @ 00:34:12` | speaker + topic ("WS-1, Janet on checkout") |
| RFP / Brief / docs | section or page (`RFP §3.2`) | heading text |
| FigJam / board export | frame or sticky text (`FJ-1, "Must-have" frame`) | board section |
| Meeting notes | bullet/heading | date + topic |

Never invent a locator. A vague-but-true locator beats a precise-but-fabricated one. If a source can't support citations at all (e.g., an unlabeled photo of a whiteboard), list it in the index and treat claims that rest only on it as unverified (→ Known Unknowns).

## 2. Extraction discipline

Work through the template section by section. For each candidate item:

1. **Can I cite it?** If no source supports it, it is not a requirement -- it's a question. Write it as a KU- item ("Stakeholders implied X but never stated it; confirm"). This is the anti-hallucination rule and it has no exceptions.
2. **Is it WHAT or HOW?** "Orders must appear in NetSuite within 5 minutes" → IR (what + SLA). "Integrate via SuiteQL" → out, flag for TDD. "The client's stack is NetSuite and that's not changing" → CON.
3. **Is it one thing?** Split compound statements. "Users can search and filter products" is two FRs.
4. **Where does it live?** Common misfiles: content ownership statements are CR- items not FRs; "the client wants it fast" is an NFR needing a number or a KU asking for one; "launch before the holiday season" is a CON; anything a stakeholder raised that the budget can't hold goes to Out of Scope with a disposition, never silently dropped.

For every FR, draft acceptance criteria in Given/When/Then -- and force at least one failure or edge path. Stakeholders narrate happy paths; the failure paths usually have to be inferred. Inferring a failure path is allowed (it's derived from the stated behavior, cite the same source); inventing a new behavior is not.

Priorities: if the corpus includes MoSCoW sorting (common in FigJam workshop boards), use it and cite the board. If not, do not guess priorities -- mark them `must` only where the source is explicit, otherwise leave priority as a question in the question pass.

## 3. Conflict handling

When two sources disagree (or one stakeholder disagrees with themselves across sessions):

- Log it in Section 13 with both citations and a neutral statement of the tension.
- If a clear resolution exists in the corpus (e.g., a later session explicitly revisits and decides), record the resolution with its source and mark resolved.
- Otherwise leave it open. Open conflicts block approval by design -- that's the forcing function for a human decision.
- Pick the more conservative reading for any draft content that depends on the conflict, and note that you did.

## 4. The question pass

Before finalizing, sweep for gaps and rank them by how much of the document they block:

- Objectives without a measurable success criterion or baseline
- FRs with no failure path you could responsibly infer
- No named decision-maker (Section 12)
- Content ownership unstated (the classic agency schedule killer)
- Constraints implied but never confirmed (budget range, hard dates)

Ask the user the top questions directly -- cap around 7, highest value first. Everything else becomes a KU- row with `assigned_to: TBD`. Do not block generation waiting for answers; ship v0.1 with honest gaps.

## 5. Output hygiene

- Strip every HTML guidance comment from the final Markdown.
- Write Section 2 (Summary) last, one page max, plain words.
- Default NFRs (WCAG 2.2 AA, analytics instrumentation) stay unless explicitly waived; record waivers in Section 13.
- Derive `prd-data.yaml`, run `scripts/validate_prd.py`, and fix every failure before presenting. If fixing means downgrading an item (unsourced FR → KU), say so in your report.
- Report to the user: counts per section, open KUs, open conflicts, questions asked, items routed somewhere they might not expect.