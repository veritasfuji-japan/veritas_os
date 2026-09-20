# Reproducible Decision-to-Effect E2E Evidence

This directory is the stable repository location for the TASK-007 proof
contract. The machine-readable proof files themselves are generated on each
dedicated GitHub Actions run so they can bind the exact source SHA, ephemeral
controlled CA, decisions, authorizations, PostgreSQL operations and receipt
hashes from that run.

## Workflow

`.github/workflows/reproducible-decision-to-effect-e2e.yml`

Required check:

`reproducible-decision-to-effect-e2e`

## Commit identity and execution conditions

Both dedicated proof workflows run on every pull request, every push to
`main`, and manual dispatch. There are no path filters: API, policy, storage,
migration and dependency changes can affect the proof indirectly.

Both `report.json` and `evidence.json` record:

- `tested_sha`: actual `git rev-parse HEAD`, required to equal the workflow's
  `github.sha`;
- `source_sha`: PR head SHA (retained for compatibility); and
- `base_sha`: PR base SHA.

On a PR, `tested_sha` normally identifies GitHub's synthetic merge commit and
can differ from both metadata SHAs. On a main push or manual dispatch, all three
identify the event's commit. Missing, malformed or mismatched identities fail
the proof; the final artifact check independently verifies both files against
the checkout and event metadata, even if the files agree with each other.

A passing PR run is evidence for its tested merge candidate. Evidence for a
merged main commit requires a successful main run with that exact `tested_sha`.
Failed-run artifacts may still be uploaded for diagnosis and are not PASS
evidence. These fields are CI provenance, not signed attestations or additional
execution authority.

## Generated artifacts

### report.json

A compact proof report containing:

- tested checkout, source and base commit SHAs;
- deployment and controlled CA digests;
- Alembic revision;
- normal-path decision / promotion / authorization / operation identities;
- fault-path decision / promotion / authorization / operation identities;
- reconciliation evidence and receipt-bundle hashes;
- a machine-checkable proof conjunction;
- an evidence hash; and
- a proof-manifest hash.

### evidence.json

The detailed synthetic evidence bundle for both normal and fault cases:

- verified CanonicalDecisionArtifact;
- canonical verified promotion packet;
- native v2 authorization artifact;
- durable authorization-consumption record;
- archived reconciliation evidence; and
- deterministic BindReceipt / Outcome bundle.

Bearer material and private keys must never appear in either artifact.

## Required scenarios

### Normal

`/v1/decide -> CDA -> promotion -> native v2 authorization -> consume ->
current rechecks -> real TLS POST -> PostgreSQL persistence -> read-only
reconciliation -> receipt/outcome`

### Fault

A real TLS POST commits the sandbox event, but the caller loses the observed
response. Durable state remains `EFFECT_UNKNOWN`. A controlled read-only lookup
outage must leave it unknown with retry prohibited. After lookup recovery, the
same persisted operation is confirmed. No second POST is permitted, and repeat
recovery must not perform another reconciliation lookup.

## Controlled fixture timing

The shared synthetic risk fixture records issuance three seconds after decision
capture. Setup waits for actual UTC to reach that timestamp, with a five-second
monotonic timeout. Consumption and dispatch keep their real clocks and existing
fail-closed checks; an expired authorization or unhealthy clock still fails.

## Claim boundary

A passing report proves a **controlled current-head Decision-to-Effect E2E**
through real TLS and real PostgreSQL with synthetic decisions, credentials and
business effects.

It does not prove production readiness, customer integration, external clock
trust, TrustLog exactly-once publication, or regulatory status.

`STOP.md` is retained only as the historical stop record for the older proof
path.
