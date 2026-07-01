# Upsert, idempotency, tombstones, and the no-op guard

A single OpenAPI YAML file does not support the marker-anchored regions make-issues uses
or the full-regeneration ledger make-trace uses. So make-api-contracts keeps human edits
safe and re-runs idempotent with an **upsert-by-operationId** merge plus a sidecar ledger.
This is the one pattern in the skill that is genuinely new to the pipeline, so it is the
most-tested.

## Upsert by operationId

`operationId` (`<feature-slug>.<verbResource>`, e.g. `checkout.createOrder`) is the stable
key. On every build, for each authored operation:

- **absent** -> insert it.
- **present** -> replace the derived shape (method, path, request/response schemas,
  provenance stamps) and **preserve the human-owned fields** (`summary`, `description`,
  `x-notes`): an existing human value wins over the payload; the payload only seeds those
  on first create. This is the make-issues "never clobber the human region" doctrine at
  operation altitude.
- **moved** (same operationId, new path/method) -> the old slot is removed so the
  operation never duplicates.

No text splicing, no duplication: the same authored input reproduces the same file.

## The per-operation fingerprint

`x-op-fingerprint` hashes the operation's derived SHAPE only (method, path, requestBody,
responses, sorted `x-trace-req`/`x-trace-adr`, `x-integration`). Editing a `summary`,
adding `x-notes`, or bumping `x-source-version` never churns it; a changed route or
schema does. It is how a rebuild knows whether an operation's contract actually moved.

## Tombstoning (additive, per make-trace)

An operation whose requirements ALL went inactive (superseded/deferred/removed) is not
deleted -- deleting would break a mock a developer is running. Instead it is marked
`deprecated: true` + `x-status: tombstoned` and recorded `state: deleted` in the ledger.
It **resurrects** (the flags clear) when a requirement covers it again and it is
re-authored. In-scope tombstoning is written; out-of-scope orphans are reported, not
touched (detection global, writes scoped).

## The sidecar ledger

`.make-api-sync.json` records `{operationId: {op_fingerprint, source_version, feature,
state}}` -- the durable "last synced" record. It survives even if a human reformats the
YAML, and it is what a teammate reads to see what the last run did.

## The no-op guard

The only volatile field is `info.x-generated`. The build compares the new document to the
prior one with `x-generated` nulled; when they match it reuses the old timestamp, so an
unchanged rebuild is **byte-identical** and makes no git diff. `info.x-fingerprint` and
`x-contract-version` are content-derived, so they are already stable on a no-op.

## Fail-closed emptiness

If the contract previously had operations and a build would leave zero (a bad `--spec-dir`,
a parse failure), the build **aborts and writes nothing** (exit 2). Confirm a genuine
emptying with `--allow-empty`. This mirrors make-trace's emptiness guard.
