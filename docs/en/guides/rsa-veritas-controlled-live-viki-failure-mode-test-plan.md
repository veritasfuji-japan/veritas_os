# RSA ↔ VERITAS Controlled Live V.I.K.I. Failure-Mode Test Plan

## 1. Purpose

This document defines the failure-mode test plan for a future controlled live V.I.K.I. integration in the RSA ↔ VERITAS sandbox stack.

This page is documentation-only.

- This is not a test implementation.
- This is not a live integration.
- This is not a runtime implementation.
- This is not a production API endpoint.
- This does not add network calls.
- This does not add secrets or credentials.
- This does not process real KYC data.
- This does not authorize production use.

This plan must be reviewed before any controlled live runtime implementation begins.

Related pre-live artifact:
- [Controlled live V.I.K.I. observability event taxonomy fixture plan](./rsa-veritas-controlled-live-viki-observability-event-taxonomy-fixture-plan.md) (documentation-only; no runtime/tests/fixtures/live integration).

## 2. Current baseline

The following pre-live gates already exist:

- local mock ingestion receiver design
- local mock receiver test fixture plan
- local mock receiver implementation
- local mock receiver validation snapshot
- static synthetic JSON fixture-driven E2E harness
- E2E harness validation snapshot
- controlled live integration threat model
- controlled live payload schema draft
- controlled live transport/authentication design
- controlled live replay protection and correlation-id design
- controlled live redaction and observability design
- controlled live payload schema fixture examples

Current validated path:

`static synthetic JSON fixture`
→ `ingest_local_viki_mock_payload()`
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ `VERITAS decision`
→ `redacted audit output`

Notes:

- The current implemented path is local-only, synthetic-data-only, and no-network.
- This controlled live failure-mode test plan is a future test planning artifact only.
- It does not introduce live runtime behavior.
- Offline test skeleton now exists at `tests/governance/test_controlled_live_viki_failure_modes.py` (test-only, synthetic-fixture-only, no runtime/live integration).
- The failure-mode test skeleton does not introduce endpoints, network calls, credentials, replay cache implementation, logging implementation, or observability implementation.

## 3. Fixture set under review

Fixture directory:

- `tests/fixtures/controlled_live_viki_payload_schema/`

| Fixture file | Category | Expected behavior class |
| --- | --- | --- |
| `valid_safe_proceed_v1alpha1.json` | valid | schema-valid controlled-live example |
| `valid_density_throttled_v1alpha1.json` | valid | schema-valid controlled-live example |
| `valid_algorithmic_humility_engaged_v1alpha1.json` | valid | schema-valid controlled-live example |
| `valid_deferral_engaged_v1alpha1.json` | valid | schema-valid controlled-live example |
| `invalid_unknown_rsa_status_v1alpha1.json` | invalid schema | fail closed |
| `invalid_missing_request_id_v1alpha1.json` | invalid schema | fail closed |
| `invalid_missing_correlation_id_v1alpha1.json` | invalid schema | fail closed |
| `invalid_forbidden_chain_of_thought_v1alpha1.json` | forbidden field | fail closed or reject before persistence |
| `invalid_secret_access_token_v1alpha1.json` | forbidden secret | fail closed or reject before persistence |
| `invalid_raw_kyc_record_v1alpha1.json` | forbidden regulated data | fail closed or reject before persistence |
| `invalid_naive_timestamp_v1alpha1.json` | invalid timestamp | fail closed |
| `invalid_payload_issued_at_future_skew_v1alpha1.json` | timestamp freshness | fail closed if beyond reviewed skew |
| `invalid_duplicate_request_id_scenario_a_v1alpha1.json` | replay scenario baseline | first observed request in replay window scenario |
| `invalid_duplicate_request_id_scenario_b_v1alpha1.json` | replay duplicate | fail closed if scenario A is already observed |
| `invalid_unsupported_schema_version.json` | unsupported schema | fail closed |

## 4. Test layers to cover

### Layer 1: fixture syntax validation

- All fixture files must be valid JSON.
- Fixture inventory must match manifest.
- No real secrets.
- No real KYC data.
- No real customer data.

### Layer 2: schema validation

- Required fields present.
- Types valid.
- Accepted `rsa_status` values only.
- `schema_version` supported.
- `timestamp` and `payload_issued_at` valid.

### Layer 3: transport/authentication failure simulation

- missing authentication
- failed authentication
- failed signature verification
- body hash mismatch
- missing or mismatched transport metadata

### Layer 4: replay/correlation failure simulation

- missing `request_id`
- missing `correlation_id`
- duplicate `request_id`
- same `request_id` with different `correlation_id`
- replay cache unavailable
- stale `payload_issued_at`
- future `payload_issued_at` beyond skew

### Layer 5: redaction/observability failure simulation

- chain-of-thought detected
- hidden model state detected
- `access_token` detected
- raw KYC record detected
- raw Authorization header logging attempted
- raw payload logging attempted

### Layer 6: upstream availability failure simulation

- V.I.K.I. timeout
- V.I.K.I. unreachable
- connection refused
- partial response
- missing payload

### Layer 7: VERITAS decision safety checks

- invalid input never becomes `SAFE_PROCEED`
- `SAFE_PROCEED` does not equal final commit approval
- VERITAS commit gate remains authoritative
- fail-closed state maps to `PAUSE_FOR_HUMAN_REVIEW` and `SUSPENDED_NOT_COMMITTED`

## 5. Positive fixture test expectations

| Fixture | Expected rsa_status | Expected high-level outcome | Commit gate note |
| --- | --- | --- | --- |
| `valid_safe_proceed_v1alpha1.json` | `SAFE_PROCEED` | may continue to bind-boundary evaluation | not final commit approval |
| `valid_density_throttled_v1alpha1.json` | `DENSITY_THROTTLED` | continue with upstream intervention logged | not final commit approval |
| `valid_algorithmic_humility_engaged_v1alpha1.json` | `ALGORITHMIC_HUMILITY_ENGAGED` | pause for human review | not final commit approval |
| `valid_deferral_engaged_v1alpha1.json` | `DEFERRAL_ENGAGED` | block final commit | not final commit approval |

- Positive fixture tests must still verify that `SAFE_PROCEED` is not treated as final commit approval.
- Positive fixture tests must still verify redacted audit behavior.
- Positive fixture tests must not require live V.I.K.I. transport.

## 6. Schema failure test expectations

| Failure | Fixture | Expected behavior |
| --- | --- | --- |
| unknown `rsa_status` | `invalid_unknown_rsa_status_v1alpha1.json` | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| missing `request_id` | `invalid_missing_request_id_v1alpha1.json` | fail closed |
| missing `correlation_id` | `invalid_missing_correlation_id_v1alpha1.json` | fail closed |
| unsupported `schema_version` | `invalid_unsupported_schema_version.json` | fail closed |
| naive `timestamp` | `invalid_naive_timestamp_v1alpha1.json` | fail closed |
| future `payload_issued_at` beyond skew | `invalid_payload_issued_at_future_skew_v1alpha1.json` | fail closed when threshold exceeded |

## 7. Forbidden content test expectations

| Forbidden content | Fixture | Expected behavior |
| --- | --- | --- |
| chain-of-thought | `invalid_forbidden_chain_of_thought_v1alpha1.json` | reject before persistence or fail closed; never store chain-of-thought |
| `access_token` | `invalid_secret_access_token_v1alpha1.json` | reject before persistence or fail closed; never store `access_token` |
| raw KYC record | `invalid_raw_kyc_record_v1alpha1.json` | reject before persistence or fail closed; never store raw KYC records |

- Forbidden content must never be persisted in audit output.
- Forbidden content must never be emitted in observability events.
- Forbidden content must never be converted into `SAFE_PROCEED`.
- Detection of forbidden content should produce deterministic failure classes only.

## 8. Replay/correlation test expectations

Duplicate scenario expectations:

- `invalid_duplicate_request_id_scenario_a_v1alpha1.json` may be treated as the first observed request in a replay window.
- `invalid_duplicate_request_id_scenario_b_v1alpha1.json` reuses the same `request_id` with different `correlation_id`.
- If scenario A is already observed within the replay window, scenario B must fail closed.
- Same `request_id` with different `correlation_id` must be treated as replay/correlation mismatch.
- No `SAFE_PROCEED` inference is allowed.

Future tests must cover:

- duplicate `request_id`
- duplicate `request_id` with same body hash
- duplicate `request_id` with different body hash
- duplicate `request_id` with different `correlation_id`
- replay cache unavailable
- replay cache read failure
- replay cache write failure
- replay window not configured
- clock skew policy not configured

Expected behavior:

- fail closed
- `PAUSE_FOR_HUMAN_REVIEW`
- `SUSPENDED_NOT_COMMITTED`
- no `SAFE_PROCEED` inference

## 9. Transport/authentication failure test expectations

Future failure-mode tests must cover:

- missing authentication
- failed mTLS identity validation
- failed signed request verification
- missing key id
- unknown key id
- body hash mismatch
- header/body `request_id` mismatch
- header/body `correlation_id` mismatch
- missing `X-VERITAS-Body-SHA256` when required
- malformed transport metadata

Expected behavior:

- fail closed
- `PAUSE_FOR_HUMAN_REVIEW`
- `SUSPENDED_NOT_COMMITTED`
- no `SAFE_PROCEED` inference
- no secret material logged

## 10. Timeout and upstream availability test expectations

Future failure-mode tests must cover:

- V.I.K.I. timeout
- V.I.K.I. unreachable
- connection refused
- partial response
- malformed response body
- delayed response beyond threshold
- missing payload

Expected behavior:

- fail closed
- `PAUSE_FOR_HUMAN_REVIEW`
- `SUSPENDED_NOT_COMMITTED`
- `required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE`
- no `SAFE_PROCEED` inference

## 11. Redaction and observability test expectations

Future tests must verify:

- audit output does not contain raw V.I.K.I. reasoning
- audit output does not contain raw LLM text
- audit output does not contain chain-of-thought
- audit output does not contain hidden model state
- audit output does not contain raw KYC records
- audit output does not contain customer PII
- audit output does not contain secrets or credentials
- raw Authorization header is never logged
- observability events contain deterministic result classes only
- `request_id` and `correlation_id` are preserved only when non-sensitive
- forbidden field detections are logged as deterministic classes only

## 12. Expected generic fail-closed shape

Expected generic fail-closed behavior:

- `continuation_decision: PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state: SUSPENDED_NOT_COMMITTED`
- `required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE` or `REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW` depending on failure class
- no `SAFE_PROCEED` inference
- redacted audit output
- no final commit approval

Notes:

- This document does not require one exact JSON output shape yet.
- Exact canonical output shape should be defined in a future implementation or fixture validation PR.
- The behavioral invariants above are mandatory.

## 13. Test plan matrix

| Test group | Example fixtures or simulated condition | Required result |
| --- | --- | --- |
| valid schema examples | four valid fixtures | schema-valid, no final commit approval |
| unknown status | `invalid_unknown_rsa_status_v1alpha1.json` | fail closed |
| missing `request_id` | `invalid_missing_request_id_v1alpha1.json` | fail closed |
| missing `correlation_id` | `invalid_missing_correlation_id_v1alpha1.json` | fail closed |
| forbidden chain-of-thought | `invalid_forbidden_chain_of_thought_v1alpha1.json` | fail closed or reject before persistence |
| forbidden `access_token` | `invalid_secret_access_token_v1alpha1.json` | fail closed or reject before persistence |
| forbidden raw KYC | `invalid_raw_kyc_record_v1alpha1.json` | fail closed or reject before persistence |
| naive timestamp | `invalid_naive_timestamp_v1alpha1.json` | fail closed |
| future `payload_issued_at` | `invalid_payload_issued_at_future_skew_v1alpha1.json` | fail closed if threshold exceeded |
| duplicate `request_id` | duplicate scenario A + B | fail closed on replay/correlation mismatch |
| unsupported `schema_version` | `invalid_unsupported_schema_version.json` | fail closed |
| transport auth failure | simulated missing or invalid auth | fail closed |
| integrity failure | simulated body hash mismatch | fail closed |
| upstream timeout | simulated timeout | fail closed |
| upstream unavailable | simulated unreachable middleware | fail closed |
| forbidden observability content | simulated raw log attempt | fail closed or reject before persistence |

## 14. Required implementation gates before tests

Checklist before implementing these tests:

- threat model merged
- payload schema draft merged
- transport/auth design merged
- replay/correlation design merged
- redaction/observability design merged
- payload schema fixture examples merged
- failure-mode test plan merged
- test-only feature flag defined
- synthetic-data-only test scope confirmed
- no network test strategy confirmed
- no secrets in fixtures confirmed
- redaction assertions defined
- fail-closed assertions defined

## 15. Non-goals

This plan does not permit:

- production live V.I.K.I. integration
- production API endpoint
- live transport implementation
- authentication implementation
- replay cache implementation
- observability implementation
- logging implementation
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- raw V.I.K.I. reasoning ingestion
- final commit automation based only on V.I.K.I.
- bypass of VERITAS commit gate
- secrets in repository
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 16. Compatibility preservation

- `rsa_status` remains the v1 payload field.
- `RSASandboxPayload` remains the downstream payload container.
- `evaluate_rsa_sandbox_signal()` remains the downstream evaluator.
- `upstream_signal_source` remains `"RSA"`.
- `request_id` and `correlation_id` are controlled-live schema fields, not replacements for `rsa_status`.
- `viki_status` is not introduced in this phase.
- `VIKIPayload` is not introduced in this phase.
- Any naming migration must be handled separately as v2.

## 17. What this test plan validates

- failure-mode coverage is planned before runtime implementation
- existing synthetic fixtures are mapped to expected future tests
- invalid payloads are expected to fail closed
- transport/auth failure cases are defined
- replay/correlation failure cases are defined
- redaction/observability failure cases are defined
- upstream timeout/unavailability failure cases are defined
- no live implementation is introduced

## 18. What this test plan does not validate

- it does not implement tests
- it does not implement runtime code
- it does not implement live V.I.K.I.
- it does not implement transport
- it does not implement authentication
- it does not implement replay cache
- it does not implement observability
- it does not process real KYC data
- it does not authorize production deployment

## 19. Recommended next PR after this plan

The next safe PR should be one of:

- controlled live fixture validation plan
- controlled live failure-mode test skeleton
- redaction fixture examples
- observability event taxonomy fixture plan
- controlled live integration implementation plan

Recommendation:

The safest next PR is a controlled live fixture validation plan or test skeleton that still uses only synthetic fixtures and does not add live transport.

<!-- ci-retrigger: required checks refresh only; no runtime/test/CI changes. -->
