# Corpus Intake (Gathering, before extraction)

How to assemble the discovery corpus when the user hasn't handed you the whole thing. Read this first in Generate mode, and during Amend or escalation intake whenever the trigger names material you don't have. It produces the inventory that `extraction-guide.md` assumes already exists.

The prime directive: **gather within a named scope the user confirms -- never across the whole account.** A PRD cites its sources; a corpus vacuumed from everywhere can't be cited honestly and risks dragging another client's data into the document. The Source Index is the closed set of things the PRD is allowed to cite, so building it is a deliberate, confirmed act, not a background search.

## 1. Scope first

Before searching any connected source, get a named scope from the user. One or more of:

- Project or engagement name
- Client name
- A Drive folder (link or name)
- An email thread, label, or the participants
- A date range (e.g. "discovery ran April--May 2026")

If the skill was invoked with nothing attached and no scope ("write a PRD for the Acme rebrand"), ask for the scope before doing anything else. Do not search broadly and filter afterward -- a broad search is how the wrong client's meeting ends up in the index.

If the user already pasted or linked the full corpus, skip gathering: inventory what they gave you (Section 3) and move on.

## 2. Gather within scope

Pull only what the scope names. Map each source type to where it lives:

| Source type | Where to look | Handle | Locator to capture |
|---|---|---|---|
| Workshop / meeting transcript | Calendar event for the meeting usually links the Gemini Meet transcript; also Drive | `WS-n` (workshops), `MTG-n` (other meetings) | timestamps if present; the Calendar/Drive link → `uri` |
| RFP / Brief | Drive folder named in scope | `RFP`, `BRIEF` | section or page |
| FigJam / board export | Drive folder | `FJ-n` | frame or sticky text |
| Stakeholder interview | Drive (notes/recording) or Calendar | `INT-name` | speaker + topic |
| Email thread | Gmail, scoped to the thread, label, or participants named | `EM-n` | sender + date, or subject |
| Analytics export | Drive, or supplied by the user | `AN-n` | report name + date range |

Handles follow the `extraction-guide.md` conventions, plus `EM-n` for email threads. Capture each source's link in the `uri` field of its Source Index entry whenever one exists (Drive file link, Calendar event link) -- that is how a reviewer gets back to the original.

Stay inside the scope. If a search surfaces something that looks relevant but sits outside the named scope -- a different project's folder, an unrelated thread -- do not pull it silently. List it and ask.

## 3. Confirm the Source Index before extracting

Assemble everything gathered, plus anything the user supplied directly, into a draft Appendix A (Source Index): handle, document, type, date, `uri`. Present it to the user and confirm before extraction:

- Items the user excludes are dropped from the corpus.
- Items the user adds get a handle and a row.
- Flag any source whose client or project is ambiguous, rather than assuming it belongs.

This confirmation is a **gate**. Do not begin the extraction pass (`extraction-guide.md` Section 2) until the user has signed off on the index.

## 4. Citation strength carries forward

Assess each source's citation strength as you log it -- the same discipline `extraction-guide.md` Section 1 details. A transcript without timestamps, an unlabeled notes file, or a forwarded email with no clear author gets a weaker locator, never an invented one. Claims that rest only on a source too weak to cite become Known Unknowns, not requirements.

Once the index is confirmed, hand off to `extraction-guide.md`. For a large corpus, read `orchestration.md` first -- it covers reading the sources in parallel with sub-agents.
