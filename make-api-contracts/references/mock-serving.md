# Serving the contract as a mock API

The whole point of emitting real OpenAPI 3.1 is that a mock server ingests it with **zero
conversion** -- a developer gets a live fake backend that serves the `examples` while the
real one is built. `docs/specs/api/openapi.yaml` is the file to point any OpenAPI-native
mock at.

## Stoplight Prism (no install)

```
npx @stoplight/prism-cli mock docs/specs/api/openapi.yaml
# serves on http://127.0.0.1:4010 by default
curl -s http://127.0.0.1:4010/orders -X POST -H 'content-type: application/json' -d '{}'
```

Prism returns the response `example` you authored (or generates one from the schema), and
validates requests against the contract -- so the frontend can build against the shapes
before the backend exists.

## Other OpenAPI-native mocks

- **Mockoon** -- import `openapi.yaml` (File -> Open, or the CLI `mockoon-cli`), get a
  configurable local mock with a GUI.
- **Microcks** -- upload/import `openapi.yaml` as an API artifact; it serves mocks and can
  run contract tests against a real implementation later.
- **MSW (Mock Service Worker)** -- generate handlers from the OpenAPI doc for browser/node
  test mocks.

## Why examples matter

A mock is only as useful as the response bodies it returns. make-api-contracts asks the
author to put a real `example` on each success response for exactly this reason -- the
example is served verbatim by Prism/Mockoon. Keep examples realistic; they are the
fastest signal to a frontend engineer that the contract is right.

## Keeping the mock honest

The contract is advisory and only as fresh as the last `/make-api-contracts` run. After a
requirement changes, re-run the skill (`--check` shows what drifted) so the mock reflects
the current contract. `x-source-version` on each operation records which feature version
it was built from.
