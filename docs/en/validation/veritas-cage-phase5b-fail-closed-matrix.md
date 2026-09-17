# VERITAS / CAGE Phase 5B — Verdict and Fail-Closed Runtime Matrix

## Status

Phase 5B is a source-pinned runtime verification step after the merged Phase 5A
wire proof.  It does **not** claim full Phase 5 completion.

The proof has two purposes:

1. confirm Provider03 verdict semantics over the real loopback HTTP boundary;
2. verify negative/error behavior without masking upstream CAGE exceptions with
   a VERITAS-side compatibility wrapper.

## Pinned sources

- VERITAS Phase 5A merged baseline:
  `6cb71643a4cd3aad52b6fc9a872671c070a01057`
- CAGE Phase 4 reviewed baseline:
  `5f54d5e3403d67101e028ed14fa8dade853fb221`
- CAGE source evaluated for Phase 5B:
  `8162958ac23d958871fd4016f349a7062627fd4d`

The CAGE Phase 5B source commit is pinned rather than following a moving branch.

## Runtime matrix

The primary verdict cases use the real CAGE `Provider03NormativeProvider` over
loopback HTTP to the merged VERITAS Phase 5A FastAPI surface:

- `APPROVED` -> `admitted=True`
- `ESCALATE` -> `admitted=False` plus `needs_human_review=True`
- `REJECTED` -> `admitted=False`

A local-only deterministic fault endpoint then exercises:

- unknown verdict -> hard deny
- missing verdict -> hard deny
- HTTP 500 -> `ENDPOINT_ERROR` / hard deny
- timeout -> `ENDPOINT_ERROR` / hard deny
- `action_context` legacy/canonical collision -> `MAPPING_COLLISION`, with no
  wire dispatch
- malformed JSON response
- non-string (`null`) verdict

No fault endpoint is external and no business effect is executed.

## Response-contract blocker

At the pinned CAGE source, `Provider03NormativeProvider.validate_fria()` catches
`httpx.HTTPStatusError` and `httpx.RequestError`, but does not convert JSON decode
failures into a fail-closed `ValidationResult`.

The CAGE synchronous FRIA gate wraps `provider.validate_fria(...)` with
`asyncio.wait_for(...)` and catches `asyncio.TimeoutError`; it does not provide a
generic provider-exception conversion at that boundary.

Phase 5B therefore records malformed-response exceptions as evidence.  It does
**not** add a VERITAS wrapper and then claim the CAGE boundary itself is
fail-closed.

The runtime proof also checks a `null` verdict because current Provider03 code
calls `.upper()` on the returned verdict.  A non-string verdict is therefore a
separate response-schema failure path unless the upstream adapter validates or
normalizes the response first.

Until these response-contract paths return an explicit non-admitted result (or
CAGE defines another equivalent fail-closed kernel boundary), the report status
is:

`BLOCKED_ON_CAGE_RESPONSE_FAIL_CLOSED_CONTRACT`

This status means the Phase 5B evidence run succeeded in reproducing and
localizing the blocker.  It does not mean the complete Phase 5B safety claim is
satisfied.

## Claim boundary

This proof does not claim:

- production deployment;
- a live customer integration;
- an external business effect;
- Google endorsement or corporate approval;
- a commercial integration;
- a TrustLog witness;
- that an `APPROVED` Provider03 result creates execution authority.

`APPROVED` remains an admission result only.  Execution authority remains a
separate VERITAS governance boundary.

## Evidence artifact

The CI workflow writes:

- `phase5b-runtime-report.json`
- `run-manifest.json`

The run manifest binds the evidence to the exact VERITAS and CAGE source SHAs
and records the artifact SHA-256 digest.
