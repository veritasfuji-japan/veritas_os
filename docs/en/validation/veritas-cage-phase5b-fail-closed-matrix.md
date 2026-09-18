# VERITAS / CAGE Phase 5B — Verdict and Fail-Closed Runtime Matrix

## Status

Phase 5B is the source-pinned runtime verification step after the merged Phase 5A
wire proof.  The original Phase 5B run localized two CAGE Provider03 response
handling gaps.  CAGE subsequently closed those gaps in PR #217 and merged the
fix to `main`.

This closure rerun verifies the repaired upstream CAGE contract directly.  It
does **not** add a VERITAS compatibility wrapper.

Expected result:

`READY_FOR_PHASE5C`

## Pinned sources

- VERITAS Phase 5A merged baseline:
  `6cb71643a4cd3aad52b6fc9a872671c070a01057`
- CAGE Phase 4 reviewed baseline:
  `5f54d5e3403d67101e028ed14fa8dade853fb221`
- CAGE fail-closed repair PR:
  `google/cybernetic-agent-governance-engine#217`
- CAGE PR #217 merge commit:
  `2baa79687e40cf83046ef7a65e537060eb688e2d`
- CAGE source pinned for the closure rerun:
  `fcb98bef0b5faea1afcc5a430148fe065b985ef4`

The Phase 5B proof remains commit-pinned rather than following a moving branch.

## Runtime matrix

The primary verdict cases use the real CAGE `Provider03NormativeProvider` over
loopback HTTP to the merged VERITAS Phase 5A FastAPI surface:

- `APPROVED` -> `admitted=True`
- `ESCALATE` -> `admitted=False` plus `needs_human_review=True`
- `REJECTED` -> `admitted=False`

A local-only deterministic fault endpoint verifies:

- unknown verdict -> hard deny
- missing verdict -> hard deny
- HTTP 500 -> `ENDPOINT_ERROR` / hard deny
- timeout -> `ENDPOINT_ERROR` / hard deny
- legacy/canonical action-context collision -> `MAPPING_COLLISION`, with no
  wire dispatch
- malformed / non-JSON HTTP 200 -> `admitted=False` + `PARSE_ERROR`
- non-object JSON -> `admitted=False` + `PARSE_ERROR`
- null verdict -> `admitted=False`, no exception leakage
- numeric verdict -> `admitted=False`, no exception leakage

The source audit additionally requires Provider03 to retain an explicit JSON
decode guard and a generic adapter exception guard.

## Historical blocker and closure

The original Phase 5B evidence at CAGE source
`8162958ac23d958871fd4016f349a7062627fd4d` recorded:

`BLOCKED_ON_CAGE_RESPONSE_FAIL_CLOSED_CONTRACT`

because malformed JSON and non-string verdicts could raise before a
`ValidationResult` was returned.

CAGE PR #217 closed that boundary in the Provider03 adapter.  The closure rerun
therefore requires all anomalous response cases to return an explicit
non-admitted result without exception leakage.  The proof is considered closed
only when:

- all runtime fail-closed checks pass;
- all response-contract assertions pass;
- `phase5b_blockers` is empty; and
- `phase5b_status == "READY_FOR_PHASE5C"`.

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

The run manifest binds the evidence to the exact VERITAS and CAGE source SHAs,
records the artifact SHA-256 digest, and marks Phase 5C readiness only after the
full closure matrix passes.
