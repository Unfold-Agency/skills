# The make-api-contracts contract (schema, provenance, rules)

The primary artifact is `docs/product/api/openapi.yaml` -- an OpenAPI 3.1 document a
mock server ingests directly. `API-CONTRACTS.md` is a read-only human index rendered
from it, and `.make-api-sync.json` is the sidecar ledger. This file is the reference
the schema, the provenance keys, the operationId grammar, the fingerprint IN/OUT
contract, and the validator rules.

## Scope (decided)

- **Own API only.** These are the endpoints the project's OWN code implements and its
  own frontend/clients call.
- **External providers are referenced, never redefined.** Where an endpoint fans out
  to an external system (an `IR-*` requirement), the operation carries `x-trace-adr`
  and `x-integration` back-links into make-arch. Stripe's/Shopify's own API surface is
  never authored here (mock those from the provider's own OpenAPI if needed).

## Provenance vendor extensions (mirror make-issues meta stamping)

Every operation carries (`x-*` is ignored gracefully by every OpenAPI tool):

| Key | Meaning |
|---|---|
| `x-trace-req` | requirement id(s) this operation satisfies (>=1; sorted) |
| `x-feature` | the feature slug (also the operation's `tag`) |
| `x-source-version` | the `feature_version` this operation was born from |
| `x-trace-adr` | governing ADR ids (from the requirement's `governed_by`) |
| `x-integration` | `INTG-<name>` the external system this fans out to (-> make-arch) |
| `x-op-fingerprint` | sha256 over the operation's derived shape (drives upsert/no-op) |
| `x-flow` | `unconfirmed` when no make-data-flows flow covers this op's requirement |
| `x-status` | `tombstoned` when the requirement went inactive (with `deprecated: true`) |
| `x-notes` | human-owned free notes (preserved across a rebuild) |

## operationId -- the stable upsert key

`^[a-z][a-z0-9-]*\.[a-z][a-zA-Z0-9]*$` -- `<feature-slug>.<verbResource>`, e.g.
`checkout.createOrder`. Globally unique (AC-002). This, not the text, is how an
operation is matched on a later run: same operationId -> updated in place, never
duplicated. Keep it stable when the operation still means the same thing.

## Human-owned fields (preserved across a rebuild)

`summary`, `description`, `x-notes` -- the make-issues "never clobber the human
region" doctrine at operation altitude. On a rebuild, an existing human value wins
over the payload; the payload only seeds these on first create. The derived shape
(method, path, requestBody, responses, schemas, provenance) always updates.

## Fingerprints (IN/OUT), mirroring make-spec

- **Per-operation** (`x-op-fingerprint`): IN = method, path, `requestBody`, `responses`,
  sorted `x-trace-req`/`x-trace-adr`, `x-integration`. OUT = `summary`, `description`,
  `x-notes`, `x-source-version`, `x-flow`, `x-status`, `x-op-fingerprint` itself. So a
  summary edit or a version bump never churns it; a changed schema or route does.
- **Per-document** (`info.x-fingerprint`, `x-contract-version = [:12]`): sha256 over the
  whole doc minus the three volatile info keys (`x-generated`, `x-fingerprint`,
  `x-contract-version`). The fail-closed internal-drift gate (AC-006).

## Tombstoning (additive, per make-trace)

An operation whose requirements all went inactive is marked `deprecated: true` +
`x-status: tombstoned` and recorded `state: deleted` in the ledger -- never deleted
(deleting would break a running mock). It resurrects (flags cleared) when a requirement
covers it again and it is re-authored.

## Validator rules (validate_contracts.py)

AC-001 valid OpenAPI 3.1 (openapi-spec-validator if present, else structural + warn) ·
AC-002 operationId grammar + uniqueness · AC-003 provenance present · AC-004 live-trace
(non-tombstoned op resolves to an active requirement; ADRs resolve) · AC-005
source-version matches (warn) · AC-006 doc fingerprint gate (fail-closed) · AC-007
canonical form (warn) · AC-008 present + parses · AC-009 boundary guard (warn).
Exit 0 clean / 1 violations / 2 missing-or-unparseable.
