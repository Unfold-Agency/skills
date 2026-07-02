# Derivation -- specs + flows + ADRs -> OpenAPI operations

Every part of the contract is **derived** from something upstream; nothing is
hand-mapped. This is the mapping the skill applies when authoring the operations
payload that `build_contracts.py` merges.

## The sources

- **`interface`** (a make-spec requirement field) -- the data-shape / route sketch,
  e.g. `POST /orders { items, total }`. The primary seed for a path + operation.
- **`IR-*` requirements** -- integration requirements. These become own-API operations
  that fan out to an external system (they get the `x-integration` stamp).
- **make-data-flows diagrams** -- the `<!-- make-data-flows:flow ... covers=... -->`
  blocks in the feature body show which calls a feature actually makes and in what
  order. They confirm an operation exists; a requirement with an `interface` but no
  covering flow yields an operation marked `x-flow: unconfirmed`.
- **`governed_by` ADRs + the architecture.md frontmatter integrations** -- the
  `x-trace-adr` and `x-integration` back-links into make-arch.
- **EARS acceptance criteria** -- the `IF ... THEN` unwanted-behavior clause (every FR
  has one, S-011) becomes the operation's error response (e.g. a `4XX`).

## The mapping

| OpenAPI element | Derived from | Rule |
|---|---|---|
| `paths` + `operationId` | a requirement's `interface` (method + path) | one operation per HTTP-shaped interface; `operationId = <slug>.<verbResource>` |
| `tags` | the feature `slug` | one tag per feature -- the per-feature write boundary |
| request/response `schemas` + examples | the `interface` data shape + the flow's payload labels | `interface` gives field names; the flow disambiguates request vs response and which calls exist |
| which operations exist | the make-data-flows diagram (`covers=`) | an `interface` with no covering flow -> `x-flow: unconfirmed`, not dropped |
| error responses (`4XX`) | the requirement's EARS `IF ... THEN` | the failure path is a documented response |
| `x-trace-req` / `x-feature` / `x-source-version` | the requirement id / feature slug / feature_version | provenance, mirroring make-issues |
| `x-trace-adr` / `x-integration` | `governed_by` + the matching arch integration | the external-provider link, not a redefinition |

## What is NOT an operation

- **`NFR-*` / `CR-*`** with no request/response shape (e.g. "encrypt cardholder data at
  rest", "the checkout copy is bilingual"). They have no endpoint. They may attach as an
  `x-notes` line on a related operation, but never invent a path for them.
- **External-provider calls themselves.** `POST /orders` is ours; the Stripe charge it
  makes internally is Stripe's contract, referenced by `x-integration`, not authored here.

## Authoring quality

Give every operation a real request/response schema and at least one **example** on the
success response -- the example is what a mock server serves, and it is the whole payoff
of the artifact. Draw the error response from the requirement's failure criterion. Where
the requirements are silent on a shape, say so rather than inventing it, the same way
make-spec surfaces open questions.
