# RSA ↔ VERITAS Controlled Live V.I.K.I. Observability Event Taxonomy Fixture Plan

## 1. Purpose

This document defines the observability event taxonomy fixture plan for future controlled live V.I.K.I. observability fixtures.

This is documentation-only.

- This is not an observability implementation.
- This is not a logging implementation.
- This is not a telemetry implementation.
- This is not a fixture implementation.
- This is not a test implementation.
- This is not a runtime implementation.
- This is not a live integration.
- This is not a production API endpoint.
- This does not add network calls.
- This does not add secrets or credentials.
- This does not process real KYC data.
- This does not authorize production use.

This plan must be reviewed before any observability event fixture examples or tests are added.

## 2. Current baseline

The following pre-live gates already exist:

- controlled live integration threat model
- controlled live payload schema draft
- controlled live transport/authentication design
- controlled live replay protection and correlation-id design
- controlled live redaction and observability design
- controlled live payload schema fixture examples
- controlled live failure-mode test plan
- controlled live fixture validation plan
- controlled live fixture validation test skeleton
- controlled live failure-mode test skeleton

Current implemented/tested paths remain:

- local mock receiver path is local-only, synthetic-data-only, and no-network
- fixture validation tests are offline and synthetic-fixture-only
- failure-mode skeleton tests are offline and synthetic-fixture-only

No live V.I.K.I. integration exists in this phase. No observability implementation exists in this phase. No logging or telemetry implementation is introduced by this plan.

## 3. Future observability fixture boundary

`controlled live synthetic payload fixture`
→ `transport/authentication result class`
→ `message integrity result class`
→ `replay/correlation result class`
→ `schema validation result class`
→ `VERITAS decision result class`
→ `redacted synthetic observability event fixture`
→ `offline fixture validation test`
→ `offline failure-mode test`

- Observability fixtures must be synthetic.
- Observability fixtures must not contain raw payload bodies.
- Observability fixtures must not contain raw V.I.K.I. reasoning.
- Observability fixtures must not contain raw LLM text.
- Observability fixtures must not contain chain-of-thought.
- Observability fixtures must not contain hidden model state.
- Observability fixtures must not contain raw KYC records.
- Observability fixtures must not contain customer PII.
- Observability fixtures must not contain secrets or credentials.
- Observability fixtures must not authorize live integration.

## 4. Draft event taxonomy

Draft `event_type` values:

- viki_payload_received
- transport_authentication_checked
- message_integrity_checked
- replay_window_checked
- replay_cache_checked
- schema_validation_checked
- rsa_sandbox_payload_constructed
- rsa_sandbox_signal_evaluated
- veritas_decision_emitted
- human_review_required
- upstream_unavailable
- upstream_timeout
- forbidden_field_detected
- secret_like_value_detected
- regulated_data_detected
- fail_closed_emitted

- These `event_type` values are draft names only.
- Final event taxonomy must be reviewed before implementation.
- Every event fixture must include event_type.
- Every event fixture must include event_version.
- Event names must be deterministic.
- Event names must not include free-form raw reasoning or PII.

## 5. Required fields for observability event fixtures

- event_type
- event_version
- schema_version
- request_id
- correlation_id
- timestamp
- payload_issued_at
- upstream_signal_source
- veritas_continuation_decision
- veritas_reason_code
- veritas_sandbox_commit_state
- required_next_action
- final_commit_approved

Rules:
- event_version must be `"v1alpha1"` for this fixture plan.
- schema_version must be `"v1alpha1"` for controlled live payload-derived fixtures.
- upstream_signal_source must remain `"RSA"`.
- request_id and correlation_id must be synthetic and non-sensitive.
- final_commit_approved must be false in all pre-live fixtures.
- timestamp and payload_issued_at must be timezone-aware.
- required fields must not be empty.

## 6. Optional allowed fields

Optional allowed fields:
- source_environment
- source_instance_id
- rsa_status
- trigger_source
- authentication_result_class
- integrity_result_class
- replay_result_class
- schema_validation_result_class
- redaction_result_class
- forbidden_field_result_class
- latency_ms
- body_hash_prefix
- fixture_name
- fixture_classification
- failure_class
- decision_source

Rules:
- Optional fields must not contain PII.
- Optional fields must not contain secrets.
- Optional fields must not contain raw reasoning.
- body_hash_prefix must be non-reversible and must not expose raw payload.
- latency_ms must be a non-negative integer when present.
- fixture_name must refer only to synthetic fixture file names.
- fixture_classification must use deterministic result classes.

## 7. Forbidden fields and content

Forbidden fields/content:
- chain_of_thought
- hidden_model_state
- raw_llm_reasoning
- raw_viki_reasoning
- raw_llm_text
- raw_kyc_record
- customer_pii
- secrets
- credentials
- api_key
- access_token
- refresh_token
- private_key
- webhook_secret
- raw_authorization_header
- authorization
- bearer_token
- unredacted_regulated_data
- raw_payload_body
- raw_request_body
- raw_response_body
- raw_stack_trace_with_secrets

Required behavior:
- Future observability fixtures containing these fields must be invalid.
- Future observability validation tests must reject these fields.
- Forbidden fields must never be converted into SAFE_PROCEED.
- Forbidden fields must never be persisted as redacted audit output.
- Forbidden fields must never appear in observability examples except as explicitly invalid synthetic examples.

## 8. Result class taxonomy

`authentication_result_class`: AUTHENTICATED, AUTHENTICATION_FAILED, AUTHENTICATION_NOT_EVALUATED

`integrity_result_class`: INTEGRITY_VALID, INTEGRITY_FAILED, BODY_HASH_MISMATCH, INTEGRITY_NOT_EVALUATED

`replay_result_class`: NO_REPLAY_DETECTED, REPLAY_DUPLICATE_REQUEST_ID, REPLAY_CACHE_UNAVAILABLE, REPLAY_NOT_EVALUATED

`schema_validation_result_class`: SCHEMA_VALID, SCHEMA_INVALID, SCHEMA_UNSUPPORTED_VERSION, SCHEMA_UNKNOWN_RSA_STATUS, SCHEMA_MISSING_REQUIRED_FIELD, SCHEMA_INVALID_TIMESTAMP, SCHEMA_NOT_EVALUATED

`redaction_result_class`: REDACTION_VALID, FORBIDDEN_FIELD_DETECTED, SECRET_LIKE_VALUE_DETECTED, REGULATED_DATA_DETECTED, REDACTION_NOT_EVALUATED

`veritas_sandbox_commit_state`: SUSPENDED_NOT_COMMITTED

continuation decisions: CONTINUE_TO_BIND_BOUNDARY, CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED, PAUSE_FOR_HUMAN_REVIEW

These are draft classes only. Final names must be reviewed before implementation. Classes must be deterministic and must not include raw sensitive values.

## 9-11. Event categories and behavior constraints

Future valid synthetic event fixture categories include the positive path, failure path, and simulated upstream/transport path categories listed in the plan request, with names treated as category labels (not finalized filenames).

SAFE_PROCEED behavior constraints:
- `event_type = veritas_decision_emitted`
- `veritas_continuation_decision = CONTINUE_TO_BIND_BOUNDARY`
- `veritas_sandbox_commit_state = SUSPENDED_NOT_COMMITTED`
- `required_next_action = CONTINUE_BOUNDARY_EVALUATION`
- `final_commit_approved = false`
- `veritas_reason_code = UPSTREAM_SAFE_PROCEED_SIGNAL`

Fail-closed behavior constraints:
- `event_type = fail_closed_emitted` or failure-specific event
- `veritas_continuation_decision = PAUSE_FOR_HUMAN_REVIEW`
- `veritas_sandbox_commit_state = SUSPENDED_NOT_COMMITTED`
- `final_commit_approved = false`
- deterministic fail-closed `veritas_reason_code`

Expected deterministic reason_code examples include:
`CONTROLLED_LIVE_UNKNOWN_RSA_STATUS`, `CONTROLLED_LIVE_MISSING_REQUIRED_FIELD`, `CONTROLLED_LIVE_INVALID_TIMESTAMP`, `CONTROLLED_LIVE_UNSUPPORTED_SCHEMA_VERSION`, `CONTROLLED_LIVE_FORBIDDEN_FIELD_PRESENT`, `CONTROLLED_LIVE_SECRET_LIKE_VALUE_PRESENT`, `CONTROLLED_LIVE_REGULATED_DATA_PRESENT`, `CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID`, `CONTROLLED_LIVE_UPSTREAM_TIMEOUT`, `CONTROLLED_LIVE_UPSTREAM_UNAVAILABLE`, `CONTROLLED_LIVE_TRANSPORT_AUTH_FAILED`, `CONTROLLED_LIVE_MESSAGE_INTEGRITY_FAILED`, `CONTROLLED_LIVE_REPLAY_CACHE_UNAVAILABLE`.

## 12. Safe synthetic example shape

```json
{
  "event_type": "veritas_decision_emitted",
  "event_version": "v1alpha1",
  "schema_version": "v1alpha1",
  "upstream_signal_source": "RSA",
  "request_id": "req_viki_000001",
  "correlation_id": "corr_viki_veritas_000001",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "payload_issued_at": "2026-05-20T23:01:35.876Z",
  "rsa_status": "SAFE_PROCEED",
  "trigger_source": "SRC_Normal_State",
  "authentication_result_class": "AUTHENTICATED",
  "integrity_result_class": "INTEGRITY_VALID",
  "replay_result_class": "NO_REPLAY_DETECTED",
  "schema_validation_result_class": "SCHEMA_VALID",
  "redaction_result_class": "REDACTION_VALID",
  "veritas_continuation_decision": "CONTINUE_TO_BIND_BOUNDARY",
  "veritas_reason_code": "UPSTREAM_SAFE_PROCEED_SIGNAL",
  "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "CONTINUE_BOUNDARY_EVALUATION",
  "final_commit_approved": false,
  "fixture_name": "valid_safe_proceed_v1alpha1.json",
  "fixture_classification": "FIXTURE_VALID",
  "latency_ms": 42,
  "body_hash_prefix": "sha256:synthetic-prefix-only"
}
```

This is synthetic and does not authorize production logging, and it includes no raw payload, raw reasoning, KYC data, or secrets.

## 13. Invalid synthetic example shape

```json
{
  "event_type": "veritas_decision_emitted",
  "event_version": "v1alpha1",
  "schema_version": "v1alpha1",
  "request_id": "req_viki_invalid_001",
  "correlation_id": "corr_viki_veritas_invalid_001",
  "chain_of_thought": "FORBIDDEN_SYNTHETIC_EXAMPLE",
  "raw_kyc_record": "FORBIDDEN_SYNTHETIC_KYC_RECORD",
  "access_token": "FORBIDDEN_SYNTHETIC_TOKEN"
}
```

Expected behavior: reject in future fixture validation, do not persist, do not convert to SAFE_PROCEED, do not emit as valid observability event.

## 14-17. Test relationship, validation expectations, no-network, implementation gates

- Existing `test_controlled_live_viki_fixture_validation.py` validates controlled live payload schema fixtures.
- Existing `test_controlled_live_viki_failure_modes.py` maps payload fixture classifications to fail-closed expectations.
- Future observability fixture tests should remain offline, synthetic-fixture-only, and independent from runtime logging/telemetry implementations.
- Future observability fixture validation must enforce exact event inventory, required fields, recognized event taxonomy, supported versions, synthetic IDs, `final_commit_approved = false`, SAFE_PROCEED constraints, fail-closed mapping, and forbidden-field rejection.
- No-network/no-telemetry requirement applies: no live V.I.K.I., no external APIs, no credentials, no production endpoints, no telemetry SDKs, no external log writes, and no replay cache requirement.
- Required pre-implementation gates include merged design/test-plan artifacts, this taxonomy fixture plan merged, synthetic-only/no-network confirmation, forbidden-field review, taxonomy review, and no-secrets confirmation.

## 18-22. Non-goals, compatibility, validation scope, next PR

This plan does not permit production integration, runtime observability/logging/telemetry implementation, transport/auth/replay cache implementation, live or real-data handling, commit-gate bypass, compliance/regulatory/legal claims, or secret storage.

Compatibility preserved:
- `rsa_status` remains the v1 field.
- `RSASandboxPayload` remains the downstream container.
- `evaluate_rsa_sandbox_signal()` remains the downstream evaluator.
- `upstream_signal_source` remains `"RSA"`.
- `request_id`/`correlation_id` remain schema/correlation fields and do not replace `rsa_status`.
- no `viki_status` or `VIKIPayload` introduced.

Recommended next safe PR options:
- controlled live observability event fixture examples
- controlled live observability event fixture validation test skeleton
- redaction fixture examples
- controlled live integration implementation plan

Safest next PR: controlled live observability event fixture examples (synthetic-fixture-only, no runtime, no network, no logging implementation, no telemetry implementation).
