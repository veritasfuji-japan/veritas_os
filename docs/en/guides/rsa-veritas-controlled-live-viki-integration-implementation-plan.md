# RSA ↔ VERITAS Controlled Live V.I.K.I. Integration Implementation Plan

## 1. Purpose

This document defines the **future** controlled live V.I.K.I. integration implementation sequence for the RSA ↔ VERITAS sandbox stack.

This page is documentation-only and is not:

- runtime implementation
- transport implementation
- authentication implementation
- replay cache implementation
- logging or telemetry implementation
- observability runtime implementation
- live integration
- a production API endpoint

This plan does not add network calls, secrets, credentials, or real KYC data processing, and it does not authorize production use.

This plan must be reviewed before any runtime integration PR is created.

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
- controlled live runtime interface skeleton plan

Current validated paths are offline, synthetic-fixture-only, and no-network.

No live V.I.K.I. integration exists in this phase.

No runtime controlled live transport exists in this phase.

No production observability or telemetry pipeline exists in this phase.

## 3. Implementation boundary

Future implementation boundary:

controlled live V.I.K.I. response  
→ transport/authentication verification  
→ message integrity verification  
→ replay/correlation verification  
→ schema validation  
→ redaction/forbidden-content validation  
→ RSASandboxPayload construction  
→ evaluate_rsa_sandbox_signal()  
→ VERITAS decision  
→ redacted audit / observability event emission  
→ sandbox commit gate remains enforced

Safety constraints:

- SAFE_PROCEED is only an upstream signal.
- SAFE_PROCEED must never grant final commit approval.
- final_commit_approved must remain false unless a separate VERITAS commit gate approves.
- controlled live V.I.K.I. must not bypass the VERITAS commit gate.
- raw V.I.K.I. reasoning must never be ingested.
- chain-of-thought must never be ingested.
- raw KYC records must never be ingested.

## 4. Phased implementation sequence

### Phase 0 — Planning complete

- All existing docs, fixtures, and offline tests are merged.
- No runtime behavior.
- No live integration.

### Phase 1 — Runtime interface skeleton

- Add a disabled-by-default controlled live receiver interface.
- No network calls.
- No real credentials.
- No endpoint.
- No live V.I.K.I.
- Feature flag must default to disabled.
- All behavior must fail closed when disabled.

### Phase 2 — Schema validation runtime adapter

- Convert controlled live synthetic payloads into an internal validated form.
- Preserve rsa_status compatibility.
- Preserve RSASandboxPayload downstream contract.
- Reject unsupported schema_version.
- Reject unknown rsa_status.
- Reject missing request_id or correlation_id.
- Reject naive timestamps.
- Reject forbidden fields.
- Reject secret-like fields.
- Reject regulated-data fields.

### Phase 3 — Replay/correlation adapter

- Add replay/correlation validation behind disabled-by-default guard.
- request_id duplicate detection must fail closed.
- correlation_id mismatch must fail closed.
- replay cache unavailable must fail closed.
- No production replay cache in the first runtime PR unless separately reviewed.

### Phase 4 — Transport/authentication adapter

- Add transport/authentication verification behind disabled-by-default guard.
- Authentication failure must fail closed.
- Message integrity failure must fail closed.
- No real credentials in repository.
- No production endpoint in repository.
- No automatic retry loops without review.

### Phase 5 — Redacted audit and observability adapter

- Add redacted event construction only after fixture examples and validation tests exist.
- Do not log raw payload bodies.
- Do not log chain-of-thought.
- Do not log hidden model state.
- Do not log raw KYC records.
- Do not log secrets or credentials.
- Observability output must match fixture taxonomy.

### Phase 6 — Controlled live dry-run

- Use a non-production controlled environment.
- Use synthetic or approved test data only.
- No real customer KYC data.
- No production AML/KYC claims.
- All outcomes remain SUSPENDED_NOT_COMMITTED.
- Human review remains required for fail-closed cases.

### Phase 7 — Reviewed limited live pilot

- Only after separate approval.
- Requires security review.
- Requires data-handling review.
- Requires rollback plan.
- Requires explicit operational owner.
- Requires audit review.
- Requires no secrets in repository.
- Requires no raw KYC or raw reasoning in logs.

## 5. Required feature flags and default state

Planned flags:

- VERITAS_CONTROLLED_LIVE_VIKI_ENABLE
- VERITAS_CONTROLLED_LIVE_VIKI_TRANSPORT_ENABLE
- VERITAS_CONTROLLED_LIVE_VIKI_OBSERVABILITY_ENABLE
- VERITAS_CONTROLLED_LIVE_VIKI_REPLAY_CACHE_ENABLE

Rules:

- All flags must default to disabled.
- Disabled state must fail closed.
- Tests must verify default-disabled behavior before live behavior.
- Flags must not enable production behavior by default.
- Flags must not store credentials.
- Flags must not contain endpoint URLs.

## 6. Fail-closed requirements

The following conditions must fail closed:

- disabled feature flag
- unsupported schema_version
- unknown rsa_status
- missing request_id
- missing correlation_id
- invalid timestamp
- future payload_issued_at beyond reviewed skew
- stale payload_issued_at beyond replay window
- duplicate request_id
- correlation_id mismatch
- replay cache unavailable
- authentication failure
- message integrity failure
- upstream timeout
- upstream unavailable
- forbidden field detected
- secret-like value detected
- regulated data detected
- raw reasoning detected
- raw KYC detected
- malformed payload
- invalid JSON
- unexpected exception

Fail-closed output:

- veritas_continuation_decision: PAUSE_FOR_HUMAN_REVIEW
- veritas_sandbox_commit_state: SUSPENDED_NOT_COMMITTED
- final_commit_approved: false
- required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE or REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW

## 7. Compatibility preservation

- rsa_status remains the v1 payload field.
- RSASandboxPayload remains the downstream payload container.
- evaluate_rsa_sandbox_signal() remains the downstream evaluator.
- upstream_signal_source remains "RSA".
- request_id and correlation_id are controlled-live schema/correlation fields, not replacements for rsa_status.
- viki_status is not introduced in this phase.
- VIKIPayload is not introduced in this phase.
- Any naming migration must be handled separately as v2.

## 8. Data handling constraints

Forbidden:

- real KYC data
- real customer PII
- regulated financial records
- raw V.I.K.I. reasoning
- raw LLM text
- chain-of-thought
- hidden model state
- secrets
- credentials
- API keys
- access tokens
- refresh tokens
- private keys
- webhook secrets
- authorization headers
- bearer tokens
- raw payload bodies in logs
- raw request bodies in logs
- raw response bodies in logs

Allowed in this phase:

- static synthetic fixtures
- redacted metadata
- deterministic reason codes
- synthetic request_id
- synthetic correlation_id
- synthetic fixture names
- non-reversible body_hash_prefix

## 9. Observability implementation constraints

- Observability must be redacted by default.
- Observability must not emit raw payload bodies.
- Observability must not emit raw reasoning.
- Observability must not emit KYC data.
- Observability must not emit secrets.
- Observability must not require telemetry SDKs in the first runtime skeleton.
- Observability event names must follow the taxonomy fixture plan.
- final_commit_approved must remain false in pre-live observability examples.

## 10. Test requirements before runtime implementation

Before any runtime implementation PR:

- fixture validation tests must pass
- failure-mode tests must pass
- observability event fixture validation tests must pass
- default-disabled behavior must be planned
- fail-closed behavior must be planned
- no-network tests must remain green
- no secrets in fixtures must be confirmed
- reviewer index must point to all pre-live artifacts

## 11. Required PR sequence after this plan

Recommended safe PR sequence:

1. docs: add controlled live runtime interface skeleton plan
2. tests: add controlled live default-disabled behavior test skeleton
3. runtime: add disabled-by-default controlled live receiver interface
4. tests: add controlled live schema adapter unit tests using synthetic fixtures
5. runtime: add schema adapter behind disabled feature flag
6. tests: add replay/correlation adapter unit tests
7. runtime: add replay/correlation adapter behind disabled feature flag
8. tests: add transport/authentication adapter unit tests with synthetic inputs
9. runtime: add transport/authentication adapter behind disabled feature flag
10. tests: add redacted observability event construction tests
11. runtime: add redacted observability event construction behind disabled feature flag
12. docs: add controlled live dry-run runbook
13. tests: add dry-run guard tests
14. runtime: add controlled live dry-run mode only after review

- Do not jump directly to live integration.
- Do not add network calls before the interface, schema, fail-closed, replay, and observability gates are tested.
- Do not add production credentials at any stage.

## 12. Runtime implementation acceptance criteria

Future runtime implementation PRs must prove:

- disabled by default
- no production endpoint committed
- no credentials committed
- no raw payload logging
- no raw reasoning logging
- no KYC logging
- fail-closed on all invalid states
- SAFE_PROCEED does not approve final commit
- replay/correlation failures pause
- transport/auth failures pause
- observability output is redacted
- tests pass offline
- runtime behavior is covered by targeted tests
- rollback path exists

## 13. Rollback and kill-switch expectations

- A kill switch must be available before live dry-run.
- Disable flag must force fail-closed.
- Runtime must tolerate upstream unavailability.
- Replay cache unavailable must fail closed.
- Transport/authentication unavailable must fail closed.
- No state should be committed only because V.I.K.I. returns SAFE_PROCEED.

## 14. Security review checklist

- No credentials in repository
- No production endpoint in repository
- No raw KYC in fixtures/logs
- No raw reasoning in fixtures/logs
- No chain-of-thought ingestion
- No hidden model state ingestion
- No unauthenticated transport
- No replay bypass
- No final commit automation from upstream signal alone
- No telemetry leakage
- No environment secret printed
- No exception stack trace with secrets
- No dependency audit weakening

## 15. Non-goals

This plan does not permit:

- production live V.I.K.I. integration
- production API endpoint
- live transport implementation
- authentication implementation
- replay cache implementation
- logging implementation
- telemetry implementation
- observability implementation
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

## 16. What this plan validates

- implementation sequence is defined before runtime implementation
- default-disabled behavior is required
- fail-closed behavior is required
- compatibility contract is preserved
- data-handling constraints are defined
- observability constraints are defined
- runtime PR sequence is defined
- rollback and kill-switch expectations are defined
- no live implementation is introduced

## 17. What this plan does not validate

- it does not implement runtime code
- it does not implement tests
- it does not implement transport
- it does not implement authentication
- it does not implement replay cache
- it does not implement logging
- it does not implement telemetry
- it does not implement observability runtime
- it does not connect live V.I.K.I.
- it does not process real KYC data
- it does not authorize production deployment

## 18. Recommended next PR after this plan

The safest next PR is a documentation-only controlled live runtime interface skeleton plan, followed by a test-only default-disabled behavior test skeleton.
