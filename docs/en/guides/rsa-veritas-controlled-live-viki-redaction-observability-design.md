# RSA ↔ VERITAS Controlled Live V.I.K.I. Redaction and Observability Design

## 1. Purpose

This document defines redaction and observability requirements for a future controlled live V.I.K.I. integration.

- This is documentation-only.
- This is not a live integration.
- This is not a runtime implementation.
- This is not a logging implementation.
- This is not an observability implementation.
- This is not a production API endpoint.
- This does not authorize production use.
- This does not add network calls.
- This does not add secrets or credentials.
- This does not process real KYC data.
- This does not provide legal or regulatory approval.
- This design must be reviewed before any live logging, telemetry, audit pipeline, endpoint, or live middleware implementation begins.

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

Current validated path:

`static synthetic JSON fixture`
→ `ingest_local_viki_mock_payload()`
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ `VERITAS decision`
→ `redacted audit output`

This current path remains local-only, synthetic-data-only, and no-network.

## 3. Future observability boundary

Future observability boundary:

`V.I.K.I. live middleware`
→ `RSA-compatible payload`
→ `transport/authentication event`
→ `message integrity event`
→ `replay/correlation event`
→ `schema validation event`
→ `RSASandboxPayload construction event`
→ `evaluate_rsa_sandbox_signal() result event`
→ `VERITAS decision event`
→ `redacted audit entry`
→ `optional human review event`

- Observability must not become a data leakage channel.
- Audit usefulness must be preserved without storing raw reasoning, raw LLM text, raw KYC records, secrets, credentials, or customer PII.
- Every observability event must be deterministic, minimal, and redacted.
- Logging success does not imply payload validity.
- Payload validity does not imply final commit approval.
- SAFE_PROCEED does not equal final commit approval.
- VERITAS commit gate remains authoritative.

## 4. Redaction principles

- Collect the minimum necessary fields.
- Prefer deterministic state labels over free-form text.
- Prefer reason codes over raw explanations.
- Redact raw upstream intent/action by default unless explicitly reviewed.
- Reject chain-of-thought and hidden model state.
- Reject or strip secrets and credentials before persistence.
- Never log raw Authorization headers.
- Never log raw payloads that may contain sensitive data.
- Never log raw KYC records.
- Never log live LLM text.
- Never store raw V.I.K.I. internal reasoning.
- Logs must be safe for reviewer inspection.

## 5. Fields allowed in observability events

| Field | Allowed | Notes |
| --- | --- | --- |
| event_type | Yes | Deterministic event taxonomy value only. |
| event_version | Yes | Versioned event contract metadata. |
| schema_version | Yes | Payload schema contract version metadata. |
| request_id | Yes | Primary safe per-request correlation key. |
| correlation_id | Yes | Cross-stage correlation key across controlled live checks. |
| rsa_status | Yes | Must remain v1-compatible contract naming. |
| trigger_source | Yes | Must not contain raw reasoning or PII. |
| timestamp | Yes | Deterministic event emission timestamp. |
| payload_issued_at | Yes | Deterministic upstream-issued timestamp metadata. |
| source_environment | Yes | Non-sensitive environment class only. |
| source_instance_id | Yes, constrained | Must not contain host credentials, secrets, or PII. |
| authentication_result_class | Yes | Class label only; no secret material. |
| integrity_result_class | Yes | Class label only; no signature secret material. |
| replay_result_class | Yes | Class label only; no payload disclosure. |
| schema_validation_result_class | Yes | Class label only; no forbidden value persistence. |
| veritas_continuation_decision | Yes | Deterministic VERITAS continuation state. |
| veritas_reason_code | Yes | Deterministic reason code only. |
| veritas_sandbox_commit_state | Yes | Deterministic commit-state label only. |
| required_next_action | Yes | Deterministic action guidance class only. |
| latency_ms | Yes | Numeric latency metric only. |
| body_hash_prefix | Yes, constrained | Must be non-reversible and must not expose raw payload. |

## 6. Fields forbidden in observability events

| Field / content class | Required behavior |
| --- | --- |
| chain-of-thought | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| hidden model state | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| raw V.I.K.I. reasoning | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| raw LLM text | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| raw KYC records | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| customer PII | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| secrets | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| credentials | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| access tokens | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| refresh tokens | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| private keys | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| webhook secrets | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| raw Authorization header | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| full signed secret material | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| unredacted regulated data | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| raw payload body | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| raw upstream free-form explanation | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |
| stack traces containing secrets | Reject before persistence, redact, or replace with deterministic class label; fail closed if detected. |

If forbidden content is detected in a live payload or observability event, fail closed.

## 7. Event taxonomy

Draft event types:

- `viki_payload_received`
- `transport_authentication_checked`
- `message_integrity_checked`
- `replay_window_checked`
- `replay_cache_checked`
- `schema_validation_checked`
- `rsa_sandbox_payload_constructed`
- `rsa_sandbox_signal_evaluated`
- `veritas_decision_emitted`
- `human_review_required`
- `upstream_unavailable`
- `fail_closed_emitted`

- Event names are draft names only.
- Final event taxonomy must be reviewed before implementation.
- Events must be versioned.
- Events must not contain raw reasoning, raw LLM text, raw KYC records, secrets, or credentials.

## 8. Example safe observability event

```json
{
  "event_type": "veritas_decision_emitted",
  "event_version": "v1alpha1",
  "schema_version": "v1alpha1",
  "request_id": "req_viki_000001",
  "correlation_id": "corr_viki_veritas_000001",
  "rsa_status": "SAFE_PROCEED",
  "trigger_source": "SRC_Normal_State",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "payload_issued_at": "2026-05-20T23:01:35.876Z",
  "authentication_result_class": "AUTHENTICATED",
  "integrity_result_class": "INTEGRITY_VALID",
  "replay_result_class": "NO_REPLAY_DETECTED",
  "schema_validation_result_class": "SCHEMA_VALID",
  "veritas_continuation_decision": "CONTINUE_TO_BIND_BOUNDARY",
  "veritas_reason_code": "UPSTREAM_SAFE_PROCEED_SIGNAL",
  "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "CONTINUE_BOUNDARY_EVALUATION",
  "latency_ms": 42
}
```

- This example is synthetic.
- This example does not authorize production logging.
- SAFE_PROCEED is still not final commit approval.

## 9. Example forbidden observability event

```json
{
  "event_type": "veritas_decision_emitted",
  "request_id": "req_viki_invalid_001",
  "correlation_id": "corr_viki_veritas_invalid_001",
  "chain_of_thought": "FORBIDDEN",
  "raw_kyc_record": "FORBIDDEN",
  "access_token": "FORBIDDEN"
}
```

Expected behavior:

- reject before persistence or redact before persistence
- fail closed
- do not infer SAFE_PROCEED
- never store chain-of-thought
- never store raw KYC records
- never store access tokens

## 10. Redacted audit entry relationship

Future VERITAS audit entries may preserve:

- upstream_signal_source
- event_type
- event_version
- schema_version
- request_id
- correlation_id
- rsa_status
- trigger_source
- timestamp
- payload_issued_at
- source_environment
- source_instance_id when non-sensitive
- authentication_result_class
- integrity_result_class
- replay_result_class
- schema_validation_result_class
- VERITAS continuation_decision
- VERITAS reason_code
- VERITAS sandbox_commit_state
- required_next_action

Future VERITAS audit entries must not preserve:

- raw V.I.K.I. reasoning
- raw LLM text
- chain-of-thought
- hidden model state
- raw KYC records
- customer PII
- secrets
- credentials
- tokens
- private keys
- raw Authorization header
- full signed secret material
- unredacted regulated data
- raw payload body

## 11. Failure observability

Failures must be observable without leaking sensitive data.

For each failure, log only deterministic classes:

- authentication failed
- integrity failed
- replay detected
- replay cache unavailable
- schema validation failed
- forbidden field detected
- upstream unavailable
- timeout
- fail-closed emitted

Do not log:

- raw payload
- raw secret
- raw Authorization header
- raw KYC record
- raw reasoning
- stack trace with credentials

## 12. Interaction with replay/correlation design

- request_id and correlation_id are the primary safe correlation fields.
- correlation_id links transport, replay, schema validation, VERITAS decision, and human review events.
- request_id identifies a single payload emission.
- Duplicate request_id remains a replay risk and must fail closed.
- correlation_id must not contain PII or secrets.
- Observability must preserve correlation without storing raw payload data.

## 13. Interaction with transport/authentication design

- Authentication result should be logged as a class, not as credential material.
- Signature verification result should be logged as a class, not as signature secret material.
- mTLS result should be logged as a class, not raw certificate secrets.
- Body hash may be logged only as a safe digest or safe prefix, not raw payload.
- raw Authorization headers must never be logged.
- Failed authentication must not expose secret material in logs.

## 14. Interaction with payload schema draft

- The payload schema draft defines required, optional, and forbidden fields.
- Observability must reflect schema validation result, not store forbidden fields.
- Optional raw-intent/action fields must be redacted by default.
- Forbidden fields such as chain_of_thought and hidden_model_state must fail closed or be rejected before persistence.
- schema_version must be preserved as deterministic metadata.

## 15. Log retention and access assumptions

- This document does not define production retention periods.
- Retention period must be reviewed before production.
- Access to logs must be restricted.
- Logs containing regulated metadata may require compliance review.
- Logs must not be treated as a dumping ground for raw payloads.
- Any export of logs must preserve redaction.
- Any future retention policy must include deletion/expiry behavior.

## 16. Fail-closed matrix

| Failure class | Example | Observability behavior | VERITAS behavior |
| --- | --- | --- | --- |
| Forbidden field detected | `chain_of_thought` present | Emit deterministic failure class only; never persist forbidden field content. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Secret detected in payload | token-like secret string present | Emit deterministic failure class only; never persist secret material. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Raw KYC detected | unredacted KYC object present | Emit deterministic failure class only; never persist raw KYC content. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Raw reasoning detected | upstream free-form reasoning present | Emit deterministic failure class only; never persist raw reasoning. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Chain-of-thought detected | chain-of-thought field present | Emit deterministic failure class only; never persist chain-of-thought content. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Hidden model state detected | hidden model state field present | Emit deterministic failure class only; never persist hidden state. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Authorization header logging attempted | raw header string included | Emit deterministic failure class only; never persist raw Authorization value. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Replay cache unavailable | replay cache backend timeout | Emit deterministic failure class only; never include payload body. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Authentication failed | signature mismatch | Emit deterministic failure class only; never include credentials. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Integrity failed | digest mismatch | Emit deterministic failure class only; never include raw body. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Schema validation failed | required field missing | Emit deterministic failure class only; never include full payload. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Upstream unavailable | transport endpoint unavailable | Emit deterministic failure class only; never include secret connection details. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Timeout | end-to-end wait exceeded | Emit deterministic failure class only; never include sensitive payload fragments. | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |

## 17. Required implementation gates

Checklist before any redaction/observability implementation:

- [ ] threat model merged
- [ ] payload schema draft merged
- [ ] transport/auth design merged
- [ ] replay/correlation design merged
- [ ] redaction/observability design merged
- [ ] event taxonomy finalized
- [ ] forbidden field detector plan drafted
- [ ] logging sink selected
- [ ] log retention policy drafted
- [ ] access control policy drafted
- [ ] redaction tests drafted
- [ ] failure-mode test plan drafted
- [ ] staging-only feature flag defined
- [ ] synthetic-data-only test plan drafted
- [ ] rollback plan documented
- [ ] security review completed

## 18. Non-goals

This design does not permit:

- production live V.I.K.I. integration
- production logging pipeline
- production API endpoint
- public unauthenticated endpoint
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- raw V.I.K.I. reasoning ingestion
- chain-of-thought storage
- hidden model state storage
- raw KYC logging
- final commit automation based only on V.I.K.I.
- bypass of VERITAS commit gate
- secrets in repository
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 19. Compatibility preservation

- rsa_status remains the v1 payload field.
- RSASandboxPayload remains the downstream payload container.
- evaluate_rsa_sandbox_signal() remains the downstream evaluator.
- upstream_signal_source remains "RSA".
- request_id and correlation_id are observability/correlation fields, not replacements for rsa_status.
- viki_status is not introduced in this phase.
- VIKIPayload is not introduced in this phase.
- Any naming migration must be handled separately as v2.

## 20. What this design validates

- observability risks are documented before implementation
- allowed observability fields are defined
- forbidden observability fields are defined
- redaction expectations are documented
- failure observability is documented
- audit relationship is documented
- log retention assumptions are documented
- no live implementation is introduced

## 21. What this design does not validate

- it does not implement logging
- it does not implement telemetry
- it does not implement redaction
- it does not implement forbidden field detection
- it does not implement transport
- it does not implement authentication
- it does not implement replay protection
- it does not validate production AML/KYC compliance
- it does not validate regulatory approval
- it does not provide legal advice
- it does not authorize production deployment
- it does not make VERITAS production-ready for live V.I.K.I.

## 22. Recommended next PR after this design

The next safe PR should be one of:

- live payload schema fixture examples
- controlled live failure-mode test plan
- redaction fixture examples
- controlled live integration implementation plan
- observability event taxonomy fixture plan

The safest next PR is live payload schema fixture examples, still documentation-only or fixture-only with synthetic data, because the schema, transport/auth, replay/correlation, and redaction/observability gates should be represented as concrete synthetic examples before any runtime implementation.


## Related pre-live artifact

- [Controlled live V.I.K.I. payload schema fixture examples (documentation-and-fixture-only pre-live artifact; no runtime changes, tests, or live integration).](./rsa-veritas-controlled-live-viki-payload-schema-fixture-examples.md)

## Related fixture artifact

See also: [Controlled live V.I.K.I. observability event fixture examples](./rsa-veritas-controlled-live-viki-observability-event-fixture-examples.md).
