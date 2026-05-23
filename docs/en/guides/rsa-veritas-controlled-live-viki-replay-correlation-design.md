# RSA ↔ VERITAS Controlled Live V.I.K.I. Replay Protection and Correlation-ID Design

## 1. Purpose

This document defines the replay protection and correlation-id design for a future controlled live V.I.K.I. integration.

This artifact is documentation-only.

This artifact is not a live integration.

This artifact is not a runtime implementation.

This artifact is not a replay cache implementation.

This artifact is not a production API endpoint.

This artifact does not authorize production use.

This artifact does not add network calls.

This artifact does not add secrets or credentials.

This artifact does not process real KYC data.

This artifact does not provide legal or regulatory approval.

This design must be reviewed before any replay cache, request tracking, endpoint, or live middleware implementation begins.

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

The current validated path remains:

static synthetic JSON fixture
→ ingest_local_viki_mock_payload()
→ RSASandboxPayload
→ evaluate_rsa_sandbox_signal()
→ VERITAS decision
→ redacted audit output

This current path remains local-only, synthetic-data-only, and no-network.

## 3. Future replay and correlation boundary

Future replay/correlation boundary:

V.I.K.I. live middleware
→ RSA-compatible payload with request_id and correlation_id
→ transport authentication layer
→ message integrity verification
→ timestamp / payload_issued_at validation
→ replay window check
→ replay cache duplicate check
→ VERITAS live ingestion boundary
→ schema validation
→ RSASandboxPayload
→ evaluate_rsa_sandbox_signal()
→ VERITAS decision
→ redacted audit entry
→ commit gate

Rules:

- VERITAS must treat request_id and correlation_id as untrusted until transport, integrity, replay, and schema validation pass.
- request_id uniqueness does not imply payload validity.
- correlation_id traceability does not imply final commit approval.
- SAFE_PROCEED does not equal final commit approval.
- VERITAS commit gate remains authoritative.
- Replay suspicion, duplicate request_id, stale timestamp, future timestamp beyond skew, missing IDs, malformed IDs, or replay cache failure must fail closed.

## 4. Identifier definitions

### request_id

- Unique identifier for a single V.I.K.I. payload emission / upstream request.
- Must be non-empty.
- Must not contain PII.
- Must not contain secrets.
- Must not contain raw reasoning.
- Must be unique within the replay window.
- Duplicate request_id within replay window must fail closed.

### correlation_id

- Trace identifier linking V.I.K.I. emission, VERITAS ingestion, audit entry, and human review event.
- May be shared across related events in the same review flow.
- Must be non-empty.
- Must not contain PII.
- Must not contain secrets.
- Must not contain raw reasoning.
- Must be preserved in redacted audit output when non-sensitive.

### payload_issued_at

- Timestamp when V.I.K.I. emitted the payload.
- Must be RFC 3339 UTC or timezone-aware ISO-8601 normalized to UTC.
- Must be checked against accepted skew and replay window.

### timestamp

- Primary event timestamp.
- Must be RFC 3339 UTC or timezone-aware ISO-8601 normalized to UTC.
- Must not be naive.
- Must not be invalid.

## 5. Identifier format requirements

Future implementation should define strict identifier format rules.

Recommended draft constraints:

- request_id should be an opaque string.
- correlation_id should be an opaque string.
- Minimum length should be defined before implementation.
- Maximum length should be defined before implementation.
- Allowed character set should be defined before implementation.
- IDs should not encode user identity, customer identity, KYC fields, regulated data, secrets, or raw reasoning.
- IDs should not be derived from raw PII.
- IDs should be safe for logs after redaction review.

Recommended examples:

- req_viki_000001
- corr_viki_veritas_000001

These are draft examples only.

Final ID format must be reviewed before implementation.

Invalid identifier format must fail closed.

## 6. Replay window design

The replay window must be explicitly defined before implementation.

Draft design:

- A replay window must define how long request_id values are remembered.
- Duplicate request_id within replay window must fail closed.
- request_id outside replay window must not automatically be accepted if timestamp or integrity checks fail.
- Replay window must work together with payload_issued_at and timestamp validation.
- Replay window duration must be reviewed before implementation.
- Replay cache TTL must be greater than or equal to the accepted replay window.
- Clock skew threshold must be defined and tested.

Reference current local mock rule:

- skew > 300 seconds fails closed
- skew = 300 seconds is accepted

Controlled live integration may adopt the same 300 second exclusive threshold unless changed by separate reviewed design.

Any different live threshold must be documented before implementation.

## 7. Replay cache behavior

Draft replay cache requirements:

- Store request_id for the replay window.
- Store associated correlation_id.
- Store payload_issued_at.
- Store schema_version.
- Store a safe payload hash or body digest, not raw body.
- Do not store raw payload with sensitive fields.
- Do not store raw V.I.K.I. reasoning.
- Do not store chain-of-thought.
- Do not store hidden model state.
- Do not store raw KYC records.
- Do not store secrets or credentials.

Replay cache must support:

- lookup by request_id
- duplicate detection
- TTL expiration
- redacted audit correlation
- bounded storage behavior

Replay cache failure should fail closed unless a separately reviewed degradation policy exists.

Replay cache must not become a sensitive data store.

Replay cache implementation is out of scope for this PR.

## 8. Timestamp validation

- timestamp and payload_issued_at must be parsed as RFC 3339 UTC or timezone-aware ISO-8601 normalized to UTC.
- Naive timestamps must fail closed.
- Invalid timestamps must fail closed.
- Missing timestamp must fail closed.
- Missing payload_issued_at must fail closed.
- Future timestamp beyond accepted skew must fail closed.
- Stale timestamp beyond accepted replay window must fail closed.
- timestamp and payload_issued_at mismatch policy must be defined before implementation.

Draft rule:

- If timestamp and payload_issued_at differ materially, fail closed unless a reviewed tolerance is defined.
- Material difference threshold must be defined before implementation.

## 9. Duplicate and replay failure behavior

The following must fail closed:

- missing request_id
- empty request_id
- malformed request_id
- request_id containing PII
- request_id containing secret material
- duplicate request_id within replay window
- missing correlation_id
- empty correlation_id
- malformed correlation_id
- correlation_id containing PII
- correlation_id containing secret material
- missing payload_issued_at
- invalid payload_issued_at
- stale payload_issued_at
- future payload_issued_at beyond skew
- replay cache unavailable
- replay cache write failure
- replay cache read failure
- body hash mismatch for same request_id
- correlation mismatch for same request_id

Expected generic behavior:

- continuation_decision: PAUSE_FOR_HUMAN_REVIEW
- sandbox_commit_state: SUSPENDED_NOT_COMMITTED
- required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE
- do not infer SAFE_PROCEED

## 10. Correlation across audit and review

correlation_id should link:

- V.I.K.I. payload emission
- transport authentication event
- message integrity event
- replay check event
- VERITAS schema validation event
- RSASandboxPayload construction
- evaluate_rsa_sandbox_signal() result
- VERITAS audit entry
- human review event when triggered

Audit may preserve:

- request_id
- correlation_id
- schema_version
- rsa_status
- trigger_source
- timestamp
- payload_issued_at
- replay result class
- integrity result class
- authentication result class
- VERITAS continuation_decision
- VERITAS reason_code
- VERITAS sandbox_commit_state

Audit must not preserve:

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

## 11. Interaction with transport/authentication design

- Replay protection depends on transport authentication and message integrity.
- Authentication without replay protection is insufficient.
- Replay protection without message integrity is insufficient.
- message integrity must bind request_id, correlation_id, payload_issued_at, schema_version, and body hash.
- Signed request canonicalization must include request_id and correlation_id.
- mTLS identity alone does not prevent replay unless request uniqueness is enforced.
- Transport validation must occur before schema validation.
- Schema validation must still occur after transport and replay validation.

## 12. Interaction with payload schema draft

The payload schema draft already requires:

- schema_version
- rsa_status
- trigger_source
- timestamp
- request_id
- correlation_id
- payload_issued_at

Rules:

- Replay design constrains how those fields are validated.
- request_id and correlation_id are required for traceability and replay protection.
- payload_issued_at is required for replay and freshness checks.
- schema_version must be included in signed/integrity-protected material.
- Unknown schema_version must fail closed.
- Unsupported schema_version must fail closed.

## 13. Fail-closed matrix

| Failure class | Example | Expected behavior |
| --- | --- | --- |
| Missing request_id | request_id omitted from payload | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Empty request_id | request_id = "" | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Malformed request_id | request_id has disallowed format | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Duplicate request_id | same request_id observed inside replay window | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Missing correlation_id | correlation_id omitted from payload | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Malformed correlation_id | correlation_id has disallowed format | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| request_id contains PII | request_id embeds customer name/email | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| correlation_id contains PII | correlation_id embeds customer account data | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Stale payload_issued_at | issued time older than replay window | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Future payload_issued_at beyond skew | issued time exceeds allowed forward skew | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| timestamp / payload_issued_at mismatch | materially different event times | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Replay cache unavailable | replay cache service not reachable | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Replay cache read failure | replay cache lookup error | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Replay cache write failure | replay cache persistence error | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Body hash mismatch for same request_id | same request_id with different body hash | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Correlation mismatch for same request_id | same request_id with different correlation_id | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Replay window not configured | replay window unset at startup | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Clock skew policy not configured | skew threshold unset at startup | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |

## 14. Required implementation gates

Checklist before any replay/correlation implementation:

- threat model merged
- payload schema draft merged
- transport/auth design merged
- replay/correlation design merged
- identifier format finalized
- replay window finalized
- replay cache TTL finalized
- replay cache storage selected
- replay cache failure policy finalized
- timestamp mismatch policy finalized
- correlation audit policy finalized
- security review completed
- staging-only feature flag defined
- synthetic-data-only test plan drafted
- rollback plan documented

## 15. Non-goals

This design does not permit:

- production live V.I.K.I. integration
- production replay cache
- production API endpoint
- public unauthenticated endpoint
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

- rsa_status remains the v1 payload field.
- RSASandboxPayload remains the downstream payload container.
- evaluate_rsa_sandbox_signal() remains the downstream evaluator.
- upstream_signal_source remains "RSA".
- request_id and correlation_id are pre-live schema additions, not replacements for rsa_status.
- viki_status is not introduced in this phase.
- VIKIPayload is not introduced in this phase.
- Any naming migration must be handled separately as v2.

## 17. What this design validates

- replay risks are documented before implementation
- request_id role is defined
- correlation_id role is defined
- replay window expectations are documented
- replay cache behavior is constrained
- timestamp validation expectations are documented
- duplicate request_id must fail closed
- replay cache failure must fail closed
- audit correlation expectations are defined
- no live implementation is introduced

## 18. What this design does not validate

- it does not implement replay cache
- it does not implement request tracking
- it does not implement transport
- it does not implement authentication
- it does not implement authorization
- it does not validate production AML/KYC compliance
- it does not validate regulatory approval
- it does not provide legal advice
- it does not authorize production deployment
- it does not make VERITAS production-ready for live V.I.K.I.

## 19. Recommended next PR after this design

The next safe PR should be one of:

- redaction and observability design
- live payload schema fixture examples
- controlled live failure-mode test plan
- controlled live integration implementation plan
- replay/correlation fixture examples

The safest next PR is redaction and observability design, still documentation-only, because replay/correlation fields must be logged safely without leaking sensitive payloads.


## Related pre-live artifact

- [Controlled live V.I.K.I. payload schema fixture examples (documentation-and-fixture-only pre-live artifact; no runtime changes, tests, or live integration).](./rsa-veritas-controlled-live-viki-payload-schema-fixture-examples.md)
