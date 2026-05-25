# RSA ↔ VERITAS Controlled Live V.I.K.I. Runtime Interface Skeleton Plan

## 1. Purpose

This document defines the future controlled live V.I.K.I. runtime interface skeleton.

This page is documentation-only and is not:

- runtime implementation
- endpoint implementation
- network implementation
- transport/authentication implementation
- replay cache implementation
- logging or telemetry implementation
- observability runtime implementation
- live V.I.K.I. integration

This plan does not add secrets or credentials, does not process real KYC data, and does not authorize production use.

This plan must be reviewed before any runtime interface PR is created.

## Runtime wiring status (current)

The runtime receiver is now wired to the local schema adapter in runtime code, but it remains fail-closed and not-ready:

- Runtime receiver: `veritas_os/governance/controlled_live_viki_interface.py`
- Runtime schema adapter: `veritas_os/governance/controlled_live_viki_schema_adapter.py`
- Runtime wiring tests: `tests/governance/test_controlled_live_viki_receiver_schema_adapter_wiring_runtime.py`

Behavior summary:

- Feature flag disabled (anything except exact `"true"`) still returns `CONTROLLED_LIVE_DISABLED`.
- Feature flag `"true"` runs schema adapter validation only.
- Valid schema payloads return `CONTROLLED_LIVE_SCHEMA_VALID_NOT_YET_WIRED`.
- Invalid schema payloads fail closed using schema-adapter reason-code mapping.
- `SAFE_PROCEED` remains an upstream signal only and `final_commit_approved` remains `false`.

This runtime wiring remains local/offline and does not add endpoint behavior, network behavior, live V.I.K.I. integration, credentials, replay cache implementation, logging implementation, telemetry implementation, observability runtime, or production behavior.

Test-only receiver RSA handoff wiring behavior skeleton now exists at `tests/governance/test_controlled_live_viki_receiver_rsa_handoff_wiring_behavior.py`. It is test-only and does not wire runtime behavior yet, does not open synthetic network ingestion or endpoint behavior, does not introduce network behavior or live V.I.K.I. integration, and does not introduce credentials, replay cache implementation, logging implementation, telemetry implementation, observability runtime, or production behavior. SAFE_PROCEED remains upstream-only and `final_commit_approved` remains `false`. A future explicit runtime PR may wire the receiver valid-payload path to the RSA handoff helper under fail-closed constraints.

## 2. Current baseline

The following controlled live pre-live gates already exist:

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
- controlled live observability event taxonomy fixture plan
- controlled live observability event fixture examples
- controlled live observability event fixture validation test skeleton
- controlled live integration implementation plan

Current validated paths are offline, synthetic-fixture-only, and no-network.

No runtime controlled live interface exists in this phase.

No live V.I.K.I. integration exists in this phase.

No production observability or telemetry pipeline exists in this phase.

## 3. Runtime interface skeleton boundary

Planned future interface boundary:

static or controlled input object  
→ disabled-by-default controlled live runtime interface  
→ feature-flag gate  
→ schema adapter boundary  
→ fail-closed decision object  
→ existing RSA-compatible downstream path remains unchanged

The first runtime interface skeleton must not call live V.I.K.I.

The first runtime interface skeleton must not create an API endpoint.

The first runtime interface skeleton must not perform network I/O.

The first runtime interface skeleton must not require credentials.

The first runtime interface skeleton must not write logs or telemetry.

The first runtime interface skeleton must not implement replay cache.

The first runtime interface skeleton must not bypass existing evaluator logic.

SAFE_PROCEED must never grant final commit approval.

final_commit_approved must remain false unless a separate VERITAS commit gate approves.

## 4. Planned interface responsibility

The future runtime interface skeleton may define:

- an input container for controlled live payload-like data
- a disabled-by-default entry function
- a feature-flag check
- a fail-closed output shape
- a handoff point to the future schema validation adapter
- no-network default behavior
- synthetic-input-only testability

The future runtime interface skeleton must not define:

- production HTTP endpoint
- webhook endpoint
- live V.I.K.I. client
- transport authentication implementation
- message integrity implementation
- replay cache implementation
- logging implementation
- telemetry implementation
- observability runtime implementation
- production credentials
- production endpoint URLs
- real KYC processing
- final commit automation

## 5. Planned feature flag

Primary planned flag:

- VERITAS_CONTROLLED_LIVE_VIKI_ENABLE

Rules:

- Default must be disabled.
- Missing flag must behave as disabled.
- Empty flag must behave as disabled.
- Unknown flag value must behave as disabled.
- Disabled state must fail closed.
- Enabling this flag must not by itself enable network calls.
- Enabling this flag must not by itself enable live V.I.K.I.
- Enabling this flag must not by itself enable production use.
- Enabling this flag must not bypass tests, schema validation, replay validation, transport/authentication validation, redaction, observability constraints, or commit gate controls.

## 6. Planned default-disabled behavior

When the controlled live runtime interface is disabled, future behavior must return a deterministic fail-closed result:

- veritas_continuation_decision: PAUSE_FOR_HUMAN_REVIEW
- veritas_sandbox_commit_state: SUSPENDED_NOT_COMMITTED
- final_commit_approved: false
- required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE
- veritas_reason_code: CONTROLLED_LIVE_DISABLED

Disabled must not mean silently ignored.

Disabled must not mean SAFE_PROCEED.

Disabled must not mean final approval.

Disabled must not call network.

Disabled must not call live V.I.K.I.

Disabled must not emit telemetry.

Disabled must not persist raw input.

## 7. Planned input boundary

Future runtime interface input may include only controlled-live schema-compatible fields:

- schema_version
- rsa_status
- trigger_source
- timestamp
- request_id
- correlation_id
- payload_issued_at
- synthetic metadata needed for tests

Input must not include:

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

## 8. Planned output boundary

Future runtime interface output must be deterministic and redacted.

Required output shape:

- veritas_continuation_decision
- veritas_reason_code
- veritas_sandbox_commit_state
- required_next_action
- final_commit_approved
- upstream_signal_source
- request_id
- correlation_id
- schema_version
- decision_source

Rules:

- final_commit_approved must default to false.
- veritas_sandbox_commit_state must default to SUSPENDED_NOT_COMMITTED.
- upstream_signal_source must remain "RSA".
- output must not contain raw payload body.
- output must not contain raw reasoning.
- output must not contain KYC data.
- output must not contain secrets.
- output must not contain credentials.

## 9. Planned fail-closed reason codes

Draft reason codes:

- CONTROLLED_LIVE_DISABLED
- CONTROLLED_LIVE_UNSUPPORTED_SCHEMA_VERSION
- CONTROLLED_LIVE_UNKNOWN_RSA_STATUS
- CONTROLLED_LIVE_MISSING_REQUIRED_FIELD
- CONTROLLED_LIVE_INVALID_TIMESTAMP
- CONTROLLED_LIVE_FORBIDDEN_FIELD_PRESENT
- CONTROLLED_LIVE_SECRET_LIKE_VALUE_PRESENT
- CONTROLLED_LIVE_REGULATED_DATA_PRESENT
- CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID
- CONTROLLED_LIVE_REPLAY_CACHE_UNAVAILABLE
- CONTROLLED_LIVE_TRANSPORT_AUTH_FAILED
- CONTROLLED_LIVE_MESSAGE_INTEGRITY_FAILED
- CONTROLLED_LIVE_UPSTREAM_TIMEOUT
- CONTROLLED_LIVE_UPSTREAM_UNAVAILABLE
- CONTROLLED_LIVE_UNEXPECTED_EXCEPTION

These are draft runtime-interface reason codes.

They must remain deterministic.

They must not contain raw sensitive values.

Any final mapping to core/errors.py must be reviewed in a later implementation PR.

## 10. Compatibility preservation

- rsa_status remains the v1 payload field.
- RSASandboxPayload remains the downstream payload container.
- evaluate_rsa_sandbox_signal() remains the downstream evaluator.
- upstream_signal_source remains "RSA".
- request_id and correlation_id are controlled-live schema/correlation fields, not replacements for rsa_status.
- viki_status is not introduced in this phase.
- VIKIPayload is not introduced in this phase.
- Any naming migration must be handled separately as v2.

## 11. Planned future file placement

Actual file placement is not implemented by this PR.

Possible future placement candidates:

- veritas_os/governance/controlled_live_viki_interface.py
- veritas_os/governance/controlled_live_viki_schema_adapter.py
- veritas_os/governance/controlled_live_viki_decisions.py
- tests/governance/test_controlled_live_viki_default_disabled.py
- tests/governance/test_controlled_live_viki_schema_adapter.py

These paths are planning candidates only.

This PR must not create these runtime files.

A later PR must confirm actual package layout before adding runtime code.

## 12. Required test plan before runtime interface implementation

Before runtime interface implementation, add a test-only PR for default-disabled behavior.

Future tests should verify:

- feature flag missing means disabled
- feature flag empty means disabled
- feature flag false means disabled
- unknown flag value means disabled
- disabled returns CONTROLLED_LIVE_DISABLED
- disabled returns PAUSE_FOR_HUMAN_REVIEW
- disabled returns SUSPENDED_NOT_COMMITTED
- disabled returns final_commit_approved false
- disabled does not call network
- disabled does not require credentials
- disabled does not import live client
- disabled does not write telemetry
- disabled does not persist raw payload
- SAFE_PROCEED does not grant final commit approval

## 13. Runtime interface implementation acceptance criteria

A future runtime interface implementation PR must prove:

- default disabled
- no endpoint
- no network call
- no live V.I.K.I. client
- no credentials
- no production endpoint URL
- no logging implementation
- no telemetry implementation
- no replay cache implementation
- no observability runtime implementation
- deterministic fail-closed output
- final_commit_approved false by default
- compatibility contract preserved
- targeted tests pass
- no dependency audit weakening

## 14. Non-goals

This plan does not permit:

- runtime implementation
- endpoint implementation
- live V.I.K.I. integration
- network calls
- authentication implementation
- replay cache implementation
- logging implementation
- telemetry implementation
- observability runtime implementation
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- raw V.I.K.I. reasoning ingestion
- chain-of-thought storage
- hidden model state storage
- final commit automation based only on V.I.K.I.
- bypass of VERITAS commit gate
- secrets in repository
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 15. What this plan validates

- runtime interface skeleton responsibility is defined
- default-disabled behavior is specified
- feature flag expectations are specified
- input boundary is specified
- output boundary is specified
- fail-closed reason codes are drafted
- compatibility contract is preserved
- future file placement candidates are identified
- default-disabled test plan is defined
- no runtime implementation is introduced

## 16. What this plan does not validate

- it does not implement runtime code
- it does not implement tests
- it does not implement fixtures
- it does not implement endpoints
- it does not implement transport
- it does not implement authentication
- it does not implement replay cache
- it does not implement logging
- it does not implement telemetry
- it does not implement observability runtime
- it does not connect live V.I.K.I.
- it does not process real KYC data
- it does not authorize production deployment

## 17. Recommended next PR after this plan

The safest next PR is a test-only controlled live default-disabled behavior test skeleton.

Recommended next PR title:

`tests: add controlled live V.I.K.I. default-disabled behavior skeleton`

## 10. Test-only default-disabled skeleton status

A test-only default-disabled behavior skeleton now exists at
[`tests/governance/test_controlled_live_viki_default_disabled.py`](../../../tests/governance/test_controlled_live_viki_default_disabled.py).

This addition is offline and synthetic-input-only, and does not introduce runtime behavior, endpoint behavior, network calls, credentials, replay cache implementation, logging implementation, telemetry implementation, observability runtime implementation, or live V.I.K.I. integration.

## 11. Test-only schema adapter behavior skeleton status

A test-only schema adapter behavior skeleton now exists at
[`tests/governance/test_controlled_live_viki_schema_adapter_behavior.py`](../../../tests/governance/test_controlled_live_viki_schema_adapter_behavior.py).

This addition is offline and synthetic-fixture-only, and does not introduce schema adapter runtime behavior, endpoint behavior, network calls, credentials, replay cache implementation, logging implementation, telemetry implementation, observability runtime implementation, or live V.I.K.I. integration.

## Runtime status update (2026-05-24)

A first minimal runtime module now exists at `veritas_os/governance/controlled_live_viki_interface.py`, with runtime validation in `tests/governance/test_controlled_live_viki_runtime_interface.py`.

This runtime interface is disabled by default and local in-process only. It does not introduce endpoint behavior, network behavior, live V.I.K.I. integration, credentials, replay cache, logging implementation, telemetry implementation, observability runtime, or production behavior.

## Runtime schema adapter status update

A local, pure, offline runtime schema adapter now exists at `veritas_os/governance/controlled_live_viki_schema_adapter.py`, with runtime coverage in `tests/governance/test_controlled_live_viki_schema_adapter_runtime.py`.

This adapter adds deterministic payload classification and fail-closed decision construction only. It does not add endpoint behavior, network behavior, live V.I.K.I. integration, credentials, replay cache implementation, logging implementation, telemetry implementation, observability runtime, or production behavior.

`SAFE_PROCEED` remains only an upstream signal, and adapter fail-closed decisions keep `final_commit_approved` as `false`.

## Receiver-to-schema-adapter wiring behavior test skeleton status

A **test-only** receiver schema-adapter wiring behavior skeleton now exists at `tests/governance/test_controlled_live_viki_receiver_schema_adapter_wiring_behavior.py`.

It is intentionally offline and synthetic-fixture-only, does **not** wire runtime behavior yet, and does **not** add endpoint behavior, network behavior, live V.I.K.I. integration, credentials, replay cache implementation, logging implementation, telemetry implementation, observability runtime, or production behavior.

SAFE_PROCEED remains an upstream signal only, and `final_commit_approved` remains `false` in this skeleton.

Test-only note: `tests/governance/test_controlled_live_viki_schema_valid_rsa_handoff_behavior.py` now defines an offline schema-valid RSA handoff behavior skeleton. It is test-only and does not implement runtime handoff, endpoints, network/synthetic network ingestion, live V.I.K.I. integration, credentials, replay cache implementation, logging implementation, telemetry implementation, observability runtime, or production behavior. `SAFE_PROCEED` remains an upstream signal only and `final_commit_approved` remains `false`. A later explicit runtime PR may wire this handoff path under fail-closed constraints.

## Runtime update note (schema-valid RSA handoff helper)

A local/offline schema-valid RSA handoff helper now exists at:

- `veritas_os/governance/controlled_live_viki_rsa_handoff.py`
- `tests/governance/test_controlled_live_viki_schema_valid_rsa_handoff_runtime.py`

This helper is deterministic and fail-closed. It does not open endpoint behavior, does not add network behavior or synthetic network ingestion, does not integrate live V.I.K.I., and does not introduce credentials, replay cache implementation, logging implementation, telemetry implementation, observability runtime, or production behavior. `SAFE_PROCEED` remains an upstream signal only and `final_commit_approved` remains `false`. Receiver behavior remains not-ready until a later explicit wiring PR.
