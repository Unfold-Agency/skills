# Verification (how "done" is proven)

Every requirement carries a `verification:` list -- the commitment, made
operational. The acceptance criteria state **WHAT must be true** (EARS,
`references/ears-grammar.md`); verification states **HOW that will be PROVEN**,
with what evidence. The two are different layers of the same promise, and the
validator keeps them from collapsing into each other: a verification `check`
that merely restates a criterion adds nothing -- it must name the exercise and
the evidence.

Why this exists: fingerprints prove the spec, issues, and build are mutually
*consistent*; they cannot prove the code *satisfies* the criteria. Verification
is where the spec says, at authoring time, what proof "done" requires -- the
checklist a human (or the do-work acceptance gate's as-built ledger) verifies
against, and the only concrete surface an operator has for reviewing what an
autonomous build agent actually did.

## The entry shape

```yaml
verification:                # IN the fingerprint -- changing it is a change of meaning
  - method: test             # test | demo | inspection | analysis | monitor
    check: ""                # what is exercised + what evidence shows it
    covers: positive         # positive | negative
```

## The five methods

The classic V&V four, plus production monitoring:

| Method | Proof by | Use it for |
|---|---|---|
| `test` | An automated test exercising the behavior | Anything a test can reach -- the default |
| `demo` | A scripted walkthrough a stakeholder observes | UX flows, visual/brand behavior, sign-off moments |
| `inspection` | A human examining the artifact against a checklist | Content requirements (CR), copy, configuration, docs |
| `analysis` | Reasoning/review over the design or data, not execution | Security posture, capacity math, compliance mapping |
| `monitor` | A production signal observed over time | NFRs a pre-release check cannot prove (availability, p95 latency) |

## The rules (S-014 / S-015)

- **S-014** -- every active requirement has at least one entry; `method` from the
  vocabulary above; `check` non-empty; `covers` is `positive` or `negative`.
- **S-015** -- every active **FR** has at least one `covers: negative` entry:
  how the **failure/abuse path** is proven. This mirrors S-011 (every FR has an
  `IF ... THEN` criterion): if the spec names the unwanted behavior, it must
  also name the proof that the system handles it. Happy-path-only verification
  is the abuse case nobody checked.
- **Migration** -- docs still at `schema_version: "1.0"` get one aggregated
  warning per feature instead of failures. Bump the feature to `"1.1"` and
  author verification when you next amend it; malformed entries fail at any
  version (present means opted in).

## Writing checks

A good `check` names the exercise and the observable evidence, in one line:

```yaml
# FR-CHK-002 -- criterion: IF the payment is declined, THEN the system shall
#               display a recoverable error and retain the cart.
verification:
  - method: test
    check: "integration test completes checkout with a valid card and asserts the order record"
    covers: positive
  - method: test
    check: "integration test forces a gateway decline and asserts the error banner + intact cart"
    covers: negative

# NFR-PLAT-003 -- availability
verification:
  - method: monitor
    check: "uptime alert on the health endpoint; 30-day availability >= target in the dashboard"
    covers: positive
  - method: test
    check: "deploy script smoke-tests a rollback to the previous image"
    covers: negative

# CR-API-001 -- API usage guide
verification:
  - method: inspection
    check: "guide reviewed against the shipped endpoints; every documented call runs as written"
    covers: positive
```

Guidance by kind:

- **FR** -- `test` positive + `test` negative is the default pair. Use `demo`
  when the proof is inherently visual or judgment-based (that requirement is a
  natural HITL issue downstream).
- **NFR** -- the requirement is only as real as its proof. "Tenant isolation"
  verified by `test` (a cross-tenant probe that must fail) beats an assertion;
  latency/availability usually need `monitor`.
- **IR** -- prove the integration contract from OUR side: `test` against a mock
  of the provider (see make-api-contracts), `analysis` for quota/limit fit.
- **CR** -- `inspection` against the shipped artifact; the negative case is
  usually N/A (CRs are not FRs; S-015 does not apply).

## Honest limits

Verification names the intended proof; it does not run it. Authoring
`method: test` does not create the test -- do-work builds it, and the as-built
ledger records `met` / `deferred` / `mocked` per criterion against exactly this
list. If a requirement genuinely cannot state its proof yet, that is an open
question to surface, not a blank to paper over -- never invent a check to make
the validator pass.
