# EARS Grammar (acceptance criteria)

Every acceptance criterion in a feature spec is written in **EARS** -- the Easy
Approach to Requirements Syntax. EARS gives acceptance criteria a small, fixed
set of shapes so they are unambiguous and machine-checkable. `scripts/validate_spec.py`
parses every criterion (rule S-010) and **rejects any sentence that is not one of
the five forms below** -- the test is the response verb **`shall`** plus the
leading keyword (or none, for ubiquitous).

## The five templates

| Form | Template | Use it for |
|---|---|---|
| **Ubiquitous** | `The <system> shall <response>.` | An always-on property. No trigger, no condition. |
| **Event-driven** | `WHEN <trigger>, the <system> shall <response>.` | A response to a specific event or input. |
| **State-driven** | `WHILE <in some state>, the <system> shall <response>.` | A response that holds throughout a state. |
| **Optional-feature** | `WHERE <feature is included>, the <system> shall <response>.` | Behavior present only when an optional feature is. |
| **Unwanted-behavior** | `IF <unwanted condition>, THEN the <system> shall <response>.` | Errors, failures, edge cases. **Every FR needs at least one (S-011).** |

Worked examples (one per form):

- **Ubiquitous** -- `The system shall encrypt cardholder data at rest.`
- **Event-driven** -- `WHEN the user confirms the order, the system shall create a payment intent.`
- **State-driven** -- `WHILE a payment is processing, the system shall disable the submit button.`
- **Optional-feature** -- `WHERE gift wrapping is enabled, the system shall offer a message field.`
- **Unwanted-behavior** -- `IF the payment is declined, THEN the system shall display a recoverable error and retain the cart.`

## What the validator requires

- Every criterion contains the response verb **`shall`**. A sentence without it
  (`The system encrypts data.`) is **not** EARS and fails S-010.
- The leading keyword selects the form: `WHEN` -> event, `WHILE` -> state,
  `WHERE` -> optional, `IF` -> unwanted. No leading keyword + `shall` ->
  ubiquitous.
- An `IF` with no `THEN` before the `shall` is malformed and fails S-010.
- **Every functional requirement (`FR-`) must have at least one unwanted-behavior
  (`IF ... THEN ...`) criterion** -- the failure/edge path (S-011). Stakeholders
  narrate happy paths; you infer the failure path from the stated behavior (cite
  the same source). Inventing a new behavior is not allowed; deriving its failure
  mode is.

## Writing tips

- One behavior per criterion. Split `WHEN x and y` into two when x and y are
  independent triggers.
- Keep `<system>` consistent (usually "the system"); name a subsystem only when
  the distinction matters.
- A card-encryption rule, a rate limit, a localization fallback -- all are
  expressible. If a requirement genuinely cannot be phrased in EARS, it is
  probably two requirements or a constraint; reshape it rather than bypassing the
  grammar.
