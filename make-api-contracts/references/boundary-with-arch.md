# The boundary with make-arch (own API vs external integration)

make-api-contracts and make-arch both touch integrations, so the line must be crisp or
the contract duplicates or contradicts an ADR.

## What each owns

- **make-api-contracts owns** the project's OWN request/response contracts -- the
  endpoints its own code implements and its own frontend/clients call (`POST /orders`,
  `GET /cart`).
- **make-arch owns** the *decision* to use an external system (an ADR: "use Stripe") and
  the *integration edge* in `arch-data.yaml` (the external system, direction, data).

## The seam

Where an own-API endpoint fans out to an external system (an `IR-*` requirement), the
operation carries back-links, not a redefinition:

```yaml
paths:
  /orders:
    post:
      operationId: checkout.createOrder     # OUR endpoint
      x-trace-req: [IR-CHK-001]
      x-trace-adr: [ADR-0001]                # the decision -> make-arch
      x-integration: INTG-stripe             # the external system -> make-arch
```

The Stripe API surface (`POST /v1/charges`, its fields) is **never** authored in our
`openapi.yaml`. If a developer wants to mock Stripe itself, that is a separate OpenAPI
document (Stripe publishes their own); this artifact mocks *our* `/orders` endpoint that
internally calls Stripe.

## The one-line test

> Is it an endpoint OUR code serves? -> **make-api-contracts** (author it).
> Is it a decision, or an external system's own API? -> **make-arch** (reference it by id).

## The guard

`validate_contracts.py` AC-009 warns when an operation carries `x-integration` but has no
own `FR`/`IR` requirement -- a sign it is really make-arch's integration leaking in as a
redefined endpoint. Re-anchor it to a real own-API requirement or drop it.
