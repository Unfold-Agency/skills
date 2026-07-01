---
name: make-api-contracts
description: Derive and maintain an OpenAPI 3.1 contract for the project's OWN API surface from the docs/specs requirements, the make-data-flows diagrams, and the make-arch decisions -- a mock-ready openapi.yaml plus a generated API-CONTRACTS.md index. Use this skill after make-data-flows, whenever the user wants API contracts, endpoint definitions, request/response shapes, or a mock backend to build against. Trigger it for "define the API", "what are the endpoints", "generate an OpenAPI spec", "stand up a mock API", or "update the contract after requirements changed". It targets a specific feature (--feature) and is ADVISORY -- it never gates the build. It describes the project's OWN endpoints; external providers (Stripe, Shopify) are referenced via ADR/integration, never redefined. Do NOT use it to author requirements (make-spec) or record architecture decisions (make-arch).
argument-hint: "[--feature=<slug>]... [--all] [--check] [--allow-empty] [--out docs/specs/api] [--spec-dir docs/specs]"
---

# Make API contracts

Turn the requirements into a concrete, **mock-ready API contract** for the project's
own backend. The primary artifact is an OpenAPI 3.1 document a mock server ingests
directly; a human index is rendered beside it.

```
docs/specs/api/
  openapi.yaml          # PRIMARY -- OpenAPI 3.1, mock-ready, the source of truth
  API-CONTRACTS.md      # GENERATED human index (read-only), rendered from openapi.yaml
  .make-api-sync.json   # sidecar ledger (per-operation fingerprint / version / state)
```

**The doctrine: contracts derive from the specs, and describe OUR endpoints only.**
Every operation traces back to the requirement(s) it satisfies (`x-trace-req`), the
feature it belongs to (`x-feature`), and the version it was born from
(`x-source-version`) -- the same provenance make-issues stamps on issues. External
providers (Stripe, Shopify) are **referenced** via `x-trace-adr` / `x-integration`
back-links into make-arch, never redefined here. This skill is **advisory**: it
refreshes the contract and never blocks `make-issues` or `do-work`, but it keeps its
own fail-closed fingerprint gate (AC-006) and byte-identical no-op so it never
self-corrupts.

## When it runs

After `make-data-flows` (which shows which calls a feature makes) and, normally, after
`make-arch` (whose integrations/ADRs it references). It reads the requirements'
`interface` sketches and `IR-*` integration reqs, the make-data-flows diagrams, and the
ADR index; it writes only under `docs/specs/api/`. It is not part of the build gate.

## Files in this skill

- `assets/openapi-skeleton.yaml` -- an annotated illustrative doc (shape + the `x-*`
  provenance keys). Reference only; the generator seeds a fresh doc itself.
- `assets/api-contracts-schema.md` -- **read this first**: the vendor-extension contract,
  the operationId grammar, the human-owned fields, the fingerprint IN/OUT, and AC-001..AC-009.
- `assets/API-CONTRACTS-header.md` -- the preamble spliced atop the generated markdown.
- `references/derivation.md` -- exactly how `interface` + `IR-*` + flows + ADRs map to
  operations/schemas.
- `references/boundary-with-arch.md` -- own-API vs external-integration (the anti-duplication rule).
- `references/upsert-and-idempotency.md` -- upsert-by-operationId, the ledger, tombstones, the no-op guard.
- `references/mock-serving.md` -- pointing Prism / Mockoon / Microcks at the artifact.
- `scripts/build_contracts.py` -- the engine (upsert + stamp + tombstone + render + ledger; `--check` for status).
- `scripts/validate_contracts.py` -- run after every build (AC-001..AC-009).
- `scripts/contract_fingerprint.py` -- the per-operation and per-document fingerprints.
- `scripts/contractlib.py` -- shared helpers (frontmatter/flow readers, canonical serialization).

## The status -> author -> build -> validate loop

1. **Preflight.** Confirm a spec set exists under `--spec-dir` (default `docs/specs`).
   None -> stop and point at `/make-spec`. make-data-flows should have run first (its
   diagrams tell you which calls exist); if it has not, operations are still emitted but
   marked `x-flow: unconfirmed`.
2. **Status (read-only).** `python scripts/build_contracts.py docs/specs --check`. It
   reports **stale** operations (a feature moved since its ops were stamped), **coverage
   gaps** (active requirements with an HTTP-shaped `interface` but no operation yet), and
   **tombstone candidates** (operations whose requirements went inactive). Detection is
   global even on a scoped run.
3. **Author the operations.** For each in-scope feature with a gap or staleness, read its
   requirements (`interface`, `IR-*`, EARS criteria -- the `IF ... THEN` becomes an error
   response), its make-data-flows diagrams (which calls happen), and its `governed_by`
   ADRs (for `x-trace-adr` / `x-integration`). Author each operation's shape -- method,
   path, `operationId` (`<slug>.<verbResource>`), request/response schemas, and **examples**
   (they are what makes the mock useful) -- into a JSON payload. For a large run, fan out
   one worker sub-agent per feature; the write stays central. Reference make-arch
   integrations; never redefine an external provider's API (see `references/boundary-with-arch.md`).
4. **Build (deterministic).** `python scripts/build_contracts.py docs/specs payload.json
   [--feature <slug>]...`. It upserts by `operationId` (preserving human-edited
   `summary`/`description`/`x-notes`), stamps provenance + fingerprints, tombstones
   orphans, renders `API-CONTRACTS.md`, updates the ledger, and is byte-identical on a
   no-op. `--feature` bounds writes; drift elsewhere is reported.
5. **Validate.** `python scripts/validate_contracts.py docs/specs`. Fix every FAIL. If
   `openapi-spec-validator` is installed it runs the full 3.1 check; otherwise a structural
   check runs with a warning. Staleness/boundary/canonical-form warn (advisory).
6. **Report + mock.** Point a mock server at the artifact:
   `npx @stoplight/prism-cli mock docs/specs/api/openapi.yaml`. See `references/mock-serving.md`.

## Validation rules (`validate_contracts.py`, prefix AC-)

AC-001 valid OpenAPI 3.1 · AC-002 operationId grammar + uniqueness · AC-003 provenance
present · AC-004 live-trace (a non-tombstoned op resolves to an active requirement; ADRs
resolve) · AC-005 source-version matches (warn) · AC-006 doc fingerprint gate
(fail-closed) · AC-007 canonical form (warn) · AC-008 present + parses · AC-009 boundary
guard -- an op with `x-integration` but no own FR/IR (warn). See `api-contracts-schema.md`.

## Honest limits

- **Advisory.** The contract does not gate the pipeline and is only as fresh as the last
  run; re-run after requirements change (`--check` and AC-005 surface staleness).
- **Own API only.** External-provider shapes live in the provider's own OpenAPI, not here.
- **Optional validator.** Without `openapi-spec-validator` installed, AC-001 is a
  structural check and says so -- install it (`pip install openapi-spec-validator`) for
  the full 3.1 validation.
- **Scope bounds writes, not detection.** A scoped run reports drift everywhere but writes
  only the selected features.

## Writing rules

Plain words, short sentences, no marketing language. Keep each operation minimal and
honest -- a real request/response shape with an example, and the failure response drawn
from the requirement's `IF ... THEN` criterion. Never use an em dash; use ` -- `.
