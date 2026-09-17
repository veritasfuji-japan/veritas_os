# VERITAS / CAGE Phase 5A — Runtime Wire Contract

## Status

Implementation foundation for the first source-pinned VERITAS / CAGE runtime
HTTP proof.

Phase 5A is deliberately narrower than the complete Phase 5 Runtime Prototype.
It proves that the real CAGE `Provider03NormativeProvider` HTTP client can call a
VERITAS runtime process over loopback HTTP while preserving the Phase 4 boundary
semantics that are already implemented on the CAGE side.

It does **not** prove production deployment, a customer integration, a Google
product adoption or endorsement, regulatory approval, or a live external
business effect.

## Source baselines

VERITAS implementation branch starts from:

- repository: `veritasfuji-japan/veritas_os`
- `main`: `26837ad8fbb462d4163116e41b6fdfc9dcaa9431`

CAGE Phase 4 reviewed baseline:

- repository: `google/cybernetic-agent-governance-engine`
- commit: `5f54d5e3403d67101e028ed14fa8dade853fb221`
- Provider03 path: `src/integrations/provider_03/provider.py`

At drafting time, the observed CAGE `main` was
`8162958ac23d958871fd4016f349a7062627fd4d`, and the approved Provider03
collision guard remained present there.  The proof workflow intentionally pins
the reviewed Phase 4 commit rather than floating with CAGE `main`.

## Runtime topology

```text
real CAGE Provider03 client
        |
        | HTTP over loopback
        v
VERITAS Phase 5A Provider03-compatible FastAPI surface
        |
        v
existing deterministic VERITAS AML/KYC regulated-action governance path
```

The VERITAS runtime surface exposes the current Provider03 HTTP contract:

- `GET /baseline/{region}`
- `POST /validate`
- `POST /evidence/{thread_id}`

It uses the same Bearer-token request shape used by the CAGE Provider03 client.
Startup fails closed if the prototype token is not explicitly configured.

## Decision semantics

The runtime endpoint executes the existing deterministic VERITAS
regulated-action governance path and maps its outcomes to the source-reviewed
Provider03 vocabulary:

- `commit` -> `APPROVED`
- `escalate` -> `ESCALATE`
- `block` / `refuse` -> `REJECTED`
- missing or unknown prototype scenario -> `REJECTED`

An `APPROVED` response is only a Provider03 admission result.  It is not
execution authority and this Phase 5A surface never performs an external
business effect.

## Primary runtime proof

The dedicated runner imports `Provider03NormativeProvider` directly from the
pinned CAGE checkout.  It does not use a locally reimplemented or mocked CAGE
HTTP client for the primary proof path.

The runner verifies over real loopback HTTP:

- baseline fetch;
- `APPROVED` runtime case;
- `ESCALATE` runtime case, including `needs_human_review=true` on the CAGE side;
- `REJECTED` runtime case;
- evidence submission;
- invalid Bearer token fails closed;
- unavailable endpoint fails closed;
- timeout fails closed.

No live customer, bank, IAM, sanctions, SaaS, or production target is contacted.

## Phase 4 collision guard

`MAPPING_COLLISION` remains a CAGE-side pre-dispatch invariant.  The approved
Provider03 client rejects a payload containing both a configured legacy source
key and canonical destination key before HTTP dispatch, even when the two values
are equal.

Phase 5A does not duplicate that guard inside VERITAS.  Duplicating it would
create two competing normalization authorities.  The runtime proof instead
pins the CAGE source that owns the guard.

## Evidence submission boundary

`POST /evidence/{thread_id}` returns a deterministic local prototype seal over
the thread ID, evidence hash, and Phase 5A proof identity.

That seal is **not**:

- a TrustLog witness;
- a signature;
- an authority artifact;
- a production attestation;
- proof that an external system accepted an action.

TrustLog status remains `lineage_only` unless a separate real witness-generation
path actually runs.

## Known source-review gap before full Phase 5 completion

Current CAGE Provider03 source explicitly catches JSON decoding failures in
`fetch_baseline()`, but the reviewed/current `validate_fria()` path parses the
response body without a corresponding `JSONDecodeError` fail-closed branch.

Therefore a malformed `200 application/json` response from the validation
endpoint is **not yet claimed as a passing fail-closed case** by this Phase 5A
implementation.  This is tracked as an external source-level gap to resolve or
confirm with the CAGE side before the Phase 5B fail-closed runtime proof can be
considered complete.

The VERITAS implementation must not hide this by wrapping the CAGE client and
calling that wrapper equivalent to the CAGE runtime contract.

## Reviewer artifacts

The runtime runner writes:

- `phase5a-runtime-report.json`

The CI workflow adds a source-bound run manifest containing:

- executed VERITAS SHA;
- pinned CAGE SHA;
- artifact SHA-256 identities;
- GitHub Actions run identity;
- explicit non-claim flags.

## Exit boundary

This PR establishes the Phase 5A runtime wire foundation when:

- focused VERITAS runtime-surface tests pass;
- the real pinned CAGE Provider03 client reaches the VERITAS loopback runtime;
- baseline, validation, and evidence calls succeed on the nominal path;
- invalid authentication, endpoint absence, and timeout fail closed;
- the runtime artifact is source-bound and preserved;
- no external business effect occurs.

It does not by itself close all of Phase 5.  Phase 5B must extend the runtime
negative matrix and resolve the malformed-validation-response gap before the
broader fail-closed proof is claimed complete.
