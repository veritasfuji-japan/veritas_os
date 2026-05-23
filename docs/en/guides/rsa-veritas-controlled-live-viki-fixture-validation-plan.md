# RSA ↔ VERITAS Controlled Live V.I.K.I. Fixture Validation Plan

## 1. Purpose

This document defines the fixture validation plan for the controlled live V.I.K.I. payload schema fixtures.

This is **documentation-only**.

This is **not**:
- a validation test implementation,
- a runtime implementation,
- a live integration,
- a production API endpoint,
- a network call implementation,
- a secrets or credentials introduction,
- real KYC data processing,
- or production-use authorization.

This plan must be reviewed before any fixture validation test skeleton is implemented.

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
- controlled live failure-mode test plan

Current implemented path remains:

static synthetic JSON fixture
→ ingest_local_viki_mock_payload()
→ RSASandboxPayload
→ evaluate_rsa_sandbox_signal()
→ VERITAS decision
→ redacted audit output

This path is local-only, synthetic-data-only, and no-network.

The controlled live fixture validation plan is a future test planning artifact only. It does not introduce live runtime behavior. It does not introduce test implementation.

## 3. Fixture directory under validation

Fixture directory:
- `tests/fixtures/controlled_live_viki_payload_schema/`

Requirements:
- All fixture examples are synthetic.
- No fixture may contain real customer data.
- No fixture may contain real KYC data.
- No fixture may contain real secrets.
- No fixture may contain live V.I.K.I. data.
- No fixture may require network access.
- No fixture may require credentials.
- No fixture may authorize production use.

## 4. Fixture inventory validation

| Fixture file | Category | Expected validation class |
|---|---|---|
| valid_safe_proceed_v1alpha1.json | valid | valid fixture |
| valid_density_throttled_v1alpha1.json | valid | valid fixture |
| valid_algorithmic_humility_engaged_v1alpha1.json | valid | valid fixture |
| valid_deferral_engaged_v1alpha1.json | valid | valid fixture |
| invalid_unknown_rsa_status_v1alpha1.json | invalid | expected invalid fixture |
| invalid_missing_request_id_v1alpha1.json | invalid | expected invalid fixture |
| invalid_missing_correlation_id_v1alpha1.json | invalid | expected invalid fixture |
| invalid_forbidden_chain_of_thought_v1alpha1.json | invalid | expected forbidden-field fixture |
| invalid_secret_access_token_v1alpha1.json | invalid | expected forbidden-secret fixture |
| invalid_raw_kyc_record_v1alpha1.json | invalid | expected forbidden-regulated-data fixture |
| invalid_naive_timestamp_v1alpha1.json | invalid | expected invalid timestamp fixture |
| invalid_payload_issued_at_future_skew_v1alpha1.json | invalid | expected timestamp freshness fixture |
| invalid_duplicate_request_id_scenario_a_v1alpha1.json | replay scenario | duplicate baseline fixture |
| invalid_duplicate_request_id_scenario_b_v1alpha1.json | replay scenario | duplicate replay fixture |
| invalid_unsupported_schema_version.json | invalid | expected unsupported-schema fixture |

Future validation tests must ensure this inventory is complete. Missing fixture files must fail the validation test. Unexpected extra fixture files should be reviewed before being accepted.

## 5. JSON syntax validation

Future fixture validation tests must verify:
- every fixture is valid JSON
- every fixture is a JSON object
- no fixture is an array payload unless explicitly added as an invalid fixture
- no fixture is empty
- no fixture contains comments
- no fixture relies on JSON5 or non-standard JSON syntax

Expected behavior:
- invalid JSON fixture should fail fixture validation
- malformed fixture should not be silently skipped
- fixture validation must be deterministic

## 6. Required field validation

Future validation tests must verify required fields in all valid fixtures:
- schema_version
- rsa_status
- trigger_source
- timestamp
- request_id
- correlation_id
- payload_issued_at

For valid fixtures:
- all required fields must exist
- all required fields must have the expected type
- required string fields must be non-empty
- request_id must be non-empty
- correlation_id must be non-empty
- timestamp and payload_issued_at must be timezone-aware

For invalid fixtures:
- missing required fields must be intentional and documented
- missing request_id must be represented by `invalid_missing_request_id_v1alpha1.json`
- missing correlation_id must be represented by `invalid_missing_correlation_id_v1alpha1.json`

## 7. Accepted rsa_status validation

Accepted rsa_status values are:
- SAFE_PROCEED
- DENSITY_THROTTLED
- ALGORITHMIC_HUMILITY_ENGAGED
- DEFERRAL_ENGAGED

Future validation tests must verify:
- all valid fixtures use only accepted rsa_status values
- `invalid_unknown_rsa_status_v1alpha1.json` uses an unsupported value intentionally
- unknown rsa_status must never be accepted as valid
- empty rsa_status must not be accepted
- null rsa_status must not be accepted
- multiple encoded statuses must not be accepted

## 8. schema_version validation

Current controlled live schema draft uses `schema_version = "v1alpha1"`.

- Valid fixtures must use `"v1alpha1"`.
- `invalid_unsupported_schema_version.json` intentionally uses an unsupported schema_version.

Future validation tests must verify:
- supported schema_version is accepted for valid fixtures
- unsupported schema_version is rejected
- missing schema_version is rejected if added as a future invalid fixture
- null schema_version is rejected if added as a future invalid fixture

## 9. Timestamp validation

Future validation tests must verify:
- timestamp is RFC 3339 UTC or timezone-aware ISO-8601 normalized to UTC
- payload_issued_at is RFC 3339 UTC or timezone-aware ISO-8601 normalized to UTC
- naive timestamp is rejected
- invalid timestamp string is rejected
- missing timestamp is rejected if added as a future invalid fixture
- future payload_issued_at beyond reviewed skew fails closed
- stale payload_issued_at beyond replay window fails closed if added as a future invalid fixture

Reference current local mock rule:
- skew > 300 seconds fails closed
- skew = 300 seconds is accepted

Controlled live validation may adopt the same threshold unless changed by separate reviewed design.

The fixture validation plan does not implement clock-skew logic.

## 10. request_id and correlation_id validation

Future validation tests must verify:
- request_id exists in valid fixtures
- correlation_id exists in valid fixtures
- request_id is non-empty
- correlation_id is non-empty
- request_id does not contain PII
- correlation_id does not contain PII
- request_id does not contain secrets
- correlation_id does not contain secrets
- request_id is not raw reasoning
- correlation_id is not raw reasoning

Replay scenario validation:
- `invalid_duplicate_request_id_scenario_a_v1alpha1.json` and `invalid_duplicate_request_id_scenario_b_v1alpha1.json` intentionally share the same request_id.
- scenario B must be treated as duplicate/replay if scenario A is already observed within the replay window.
- same request_id with different correlation_id must be treated as replay/correlation mismatch.

## 11. Forbidden field validation

Future validation tests must detect forbidden fields:
- chain_of_thought
- hidden_model_state
- raw_llm_reasoning
- raw_viki_reasoning
- raw_kyc_record
- customer_pii
- secrets
- credentials
- api_key
- access_token
- refresh_token
- private_key
- webhook_secret
- unredacted_regulated_data

Required behavior:
- forbidden field fixtures are expected invalid fixtures
- forbidden fields must not be accepted in valid fixtures
- forbidden fields must never be persisted in audit output
- forbidden fields must never be emitted in observability events
- forbidden fields must never be converted into SAFE_PROCEED

## 12. Secret and regulated-data validation

Future validation tests must verify:
- no fixture contains real API keys
- no fixture contains real access tokens
- no fixture contains real refresh tokens
- no fixture contains private keys
- no fixture contains webhook secrets
- no fixture contains real KYC records
- no fixture contains customer PII
- no fixture contains regulated financial data
- placeholder strings such as FORBIDDEN_SYNTHETIC_TOKEN are synthetic and intentionally invalid

State:
- Secret scanning should treat real-looking secrets as failure.
- Synthetic forbidden examples must remain obviously synthetic.
- Fixture validation must not require live secret scanners or network calls in this phase.

## 13. Optional field validation

Optional accepted fields may include:
- source_environment
- source_instance_id
- rsa_action_taken
- original_llm_intent
- upstream_confidence_class
- upstream_latency_ms
- upstream_reason_code

Future validation tests must verify:
- optional fields in valid fixtures have allowed types
- upstream_latency_ms is a non-negative integer when present
- upstream_confidence_class is one of LOW, MEDIUM, HIGH, or UNSPECIFIED when present
- optional fields do not contain raw reasoning
- optional fields do not contain PII
- optional fields do not contain secrets
- original_llm_intent and rsa_action_taken are redacted by default in audit expectations

## 14. Fixture-to-failure mapping

| Fixture | Validation failure represented | Expected class |
|---|---|---|
| invalid_unknown_rsa_status_v1alpha1.json | unknown rsa_status | schema failure |
| invalid_missing_request_id_v1alpha1.json | missing request_id | schema failure |
| invalid_missing_correlation_id_v1alpha1.json | missing correlation_id | schema failure |
| invalid_forbidden_chain_of_thought_v1alpha1.json | chain_of_thought present | forbidden field |
| invalid_secret_access_token_v1alpha1.json | access_token present | forbidden secret |
| invalid_raw_kyc_record_v1alpha1.json | raw_kyc_record present | forbidden regulated data |
| invalid_naive_timestamp_v1alpha1.json | naive timestamp | timestamp failure |
| invalid_payload_issued_at_future_skew_v1alpha1.json | future payload_issued_at beyond skew | freshness failure |
| invalid_duplicate_request_id_scenario_a_v1alpha1.json | first observed duplicate scenario payload | replay scenario baseline |
| invalid_duplicate_request_id_scenario_b_v1alpha1.json | duplicate request_id with different correlation_id | replay/correlation failure |
| invalid_unsupported_schema_version.json | unsupported schema_version | schema failure |

## 15. Expected validation result classes

Draft validation result classes:
- FIXTURE_VALID
- FIXTURE_INVALID_JSON
- FIXTURE_INVALID_SCHEMA
- FIXTURE_UNSUPPORTED_SCHEMA_VERSION
- FIXTURE_UNKNOWN_RSA_STATUS
- FIXTURE_MISSING_REQUIRED_FIELD
- FIXTURE_INVALID_TIMESTAMP
- FIXTURE_FORBIDDEN_FIELD_PRESENT
- FIXTURE_SECRET_LIKE_VALUE_PRESENT
- FIXTURE_REGULATED_DATA_PRESENT
- FIXTURE_REPLAY_SCENARIO_DUPLICATE
- FIXTURE_INVENTORY_MISMATCH

These are draft names only. Final names must be reviewed before implementation.

Result classes must be deterministic.

Result classes must not include raw payload data or secrets.

## 16. Validation output expectations

Future validation output should include:
- fixture file name
- validation result class
- deterministic reason code
- whether the fixture is expected valid or expected invalid
- whether observed result matches expected result
- no raw secrets
- no raw KYC data
- no raw reasoning
- no customer PII
- no raw payload body unless explicitly safe and reviewed

Validation output must be reviewer-friendly, deterministic, and must not become a leakage channel.

## 17. No-network validation requirement

Fixture validation must not:
- call live V.I.K.I.
- call external APIs
- require credentials
- require production endpoints
- require live transport
- require live KYC data

Fixture validation must run fully offline against static synthetic fixtures.

## 18. Relationship to failure-mode test plan

- The failure-mode test plan defines future behavioral tests.
- This fixture validation plan defines the first static validation layer.
- Fixture validation should run before failure-mode behavior tests.
- Fixture validation should ensure synthetic inputs are well-formed and intentionally classified before deeper tests consume them.
- Fixture validation does not replace runtime failure-mode tests.

## 19. Required implementation gates before fixture validation tests

Checklist:
- threat model merged
- payload schema draft merged
- transport/auth design merged
- replay/correlation design merged
- redaction/observability design merged
- payload schema fixture examples merged
- failure-mode test plan merged
- fixture validation plan merged
- no-network test strategy confirmed
- synthetic-data-only fixture scope confirmed
- fixture inventory frozen or explicitly reviewed
- result classes reviewed
- no secrets in fixtures confirmed

## 20. Non-goals

This plan does **not** permit:
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

## 21. Compatibility preservation

- rsa_status remains the v1 payload field.
- RSASandboxPayload remains the downstream payload container.
- evaluate_rsa_sandbox_signal() remains the downstream evaluator.
- upstream_signal_source remains "RSA".
- request_id and correlation_id are controlled-live schema fields, not replacements for rsa_status.
- viki_status is not introduced in this phase.
- VIKIPayload is not introduced in this phase.
- Any naming migration must be handled separately as v2.

## 22. What this fixture validation plan validates

- fixture validation requirements are planned before test implementation
- fixture inventory is explicitly defined
- JSON syntax expectations are defined
- required field expectations are defined
- accepted rsa_status expectations are defined
- timestamp expectations are defined
- request_id and correlation_id expectations are defined
- forbidden field expectations are defined
- no-network validation requirement is defined
- no live implementation is introduced

## 23. What this fixture validation plan does not validate

- it does not implement tests
- it does not implement runtime code
- it does not implement live V.I.K.I.
- it does not implement transport
- it does not implement authentication
- it does not implement replay cache
- it does not implement observability
- it does not validate runtime fail-closed behavior
- it does not process real KYC data
- it does not authorize production deployment

## 24. Recommended next PR after this plan

The next safe PR should be one of:
- controlled live fixture validation test skeleton
- controlled live failure-mode test skeleton
- redaction fixture examples
- observability event taxonomy fixture plan
- controlled live integration implementation plan

Recommended:
- The safest next PR is a controlled live fixture validation test skeleton that uses only static synthetic fixtures, runs offline, and does not add live transport.
