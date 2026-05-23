# RSA ↔ VERITAS Controlled Live V.I.K.I. Payload Schema Fixture Examples

## 1. Purpose

This document describes synthetic controlled live V.I.K.I. payload schema fixtures used as a pre-live review artifact for the RSA ↔ VERITAS sandbox stack.

This change set is documentation-and-fixture-only.

- This is not a live integration.
- This is not a runtime implementation.
- This is not a test implementation.
- This is not a production API endpoint.
- This does not add network calls.
- This does not add secrets or credentials.
- This does not process real KYC data.
- This does not authorize production use.

## 2. Fixture directory

- `tests/fixtures/controlled_live_viki_payload_schema/`

All examples in this directory are synthetic.

- No fixture contains real customer data.
- No fixture contains real KYC data.
- No fixture contains real secrets.
- No fixture contains live V.I.K.I. data.
- No fixture is used by runtime code in this PR.

## 3. Valid fixture inventory

| Fixture file | rsa_status | Expected high-level behavior |
| --- | --- | --- |
| `valid_safe_proceed_v1alpha1.json` | `SAFE_PROCEED` | Compatible with reviewed controlled-live schema expectations for an allow path under RSA-compatible contracts. |
| `valid_density_throttled_v1alpha1.json` | `DENSITY_THROTTLED` | Compatible with reviewed controlled-live schema expectations for throttled-response signaling. |
| `valid_algorithmic_humility_engaged_v1alpha1.json` | `ALGORITHMIC_HUMILITY_ENGAGED` | Compatible with reviewed controlled-live schema expectations for uncertainty/suspension signaling. |
| `valid_deferral_engaged_v1alpha1.json` | `DEFERRAL_ENGAGED` | Compatible with reviewed controlled-live schema expectations for explicit deferral signaling. |

## 4. Invalid fixture inventory

| Fixture file | Invalid condition | Expected behavior |
| --- | --- | --- |
| `invalid_unknown_rsa_status_v1alpha1.json` | Unknown `rsa_status` enum | Fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference. |
| `invalid_missing_request_id_v1alpha1.json` | Missing `request_id` | Fail closed; missing `request_id` is not accepted; no `SAFE_PROCEED` inference. |
| `invalid_missing_correlation_id_v1alpha1.json` | Missing `correlation_id` | Fail closed; missing `correlation_id` is not accepted; no `SAFE_PROCEED` inference. |
| `invalid_forbidden_chain_of_thought_v1alpha1.json` | Forbidden `chain_of_thought` field | Fail closed or reject before persistence; never store chain-of-thought; no `SAFE_PROCEED` inference. |
| `invalid_secret_access_token_v1alpha1.json` | Forbidden `access_token` field | Fail closed or reject before persistence; never store `access_token`; no `SAFE_PROCEED` inference. |
| `invalid_raw_kyc_record_v1alpha1.json` | Forbidden `raw_kyc_record` field | Fail closed or reject before persistence; never store raw KYC records; no `SAFE_PROCEED` inference. |
| `invalid_naive_timestamp_v1alpha1.json` | Naive `timestamp` (no timezone suffix) | Fail closed; naive timestamp is not accepted; no `SAFE_PROCEED` inference. |
| `invalid_payload_issued_at_future_skew_v1alpha1.json` | `payload_issued_at` beyond reviewed future skew | Fail closed if threshold is exceeded; no `SAFE_PROCEED` inference. |
| `invalid_duplicate_request_id_scenario_a_v1alpha1.json` | Duplicate scenario A baseline | May be first observed request in replay window scenario modeling. |
| `invalid_duplicate_request_id_scenario_b_v1alpha1.json` | Duplicate `request_id` with different `correlation_id` | Fail closed when A already exists in replay window; replay/correlation mismatch; no `SAFE_PROCEED` inference. |
| `invalid_unsupported_schema_version.json` | Unsupported `schema_version` | Fail closed; unsupported version is not accepted; no `SAFE_PROCEED` inference. |

## 5. What these fixtures validate

These fixtures ensure review coverage for payload-shape expectations only.

- Required fields are represented.
- Optional accepted fields are represented.
- Accepted `rsa_status` variants are represented.
- Unknown `rsa_status` fails closed.
- Missing `request_id` fails closed.
- Missing `correlation_id` fails closed.
- Forbidden chain-of-thought fails closed or is rejected before persistence.
- Forbidden `access_token` fails closed or is rejected before persistence.
- Forbidden raw KYC record fails closed or is rejected before persistence.
- Naive timestamp fails closed.
- Future `payload_issued_at` beyond reviewed skew fails closed.
- Duplicate `request_id` scenario is represented.
- Unsupported `schema_version` fails closed.
- No `SAFE_PROCEED` is inferred from invalid payloads.

## 6. What these fixtures do not validate

- They do not implement live V.I.K.I.
- They do not implement transport.
- They do not implement authentication.
- They do not implement replay cache.
- They do not implement observability.
- They do not implement redaction.
- They do not add tests.
- They do not process real KYC data.
- They do not authorize production deployment.

## 7. Recommended next PR

The next safe PR should define a controlled live failure-mode test plan or fixture validation plan, still without runtime integration.

Do not implement live transport before these fixture examples and the failure-mode plan are reviewed.
