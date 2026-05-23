# RSA ↔ VERITAS Controlled Live V.I.K.I. Transport Authentication Design

- [Controlled live V.I.K.I. replay protection and correlation-id design (required pre-live replay/correlation gate, documentation-only; no runtime changes; no live integration)](./rsa-veritas-controlled-live-viki-replay-correlation-design.md)
## 1. Purpose

This document defines the transport and authentication design for a future controlled live V.I.K.I. integration.

- This is documentation-only.
- This is not a live integration.
- This is not a runtime implementation.
- This is not a production API endpoint.
- This does not authorize production use.
- This does not add network calls.
- This does not add secrets or credentials.
- This does not process real KYC data.
- This does not provide legal or regulatory approval.
- This design must be reviewed before any transport, endpoint, credential, or live middleware implementation begins.

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

Current validated path:

static synthetic JSON fixture
→ `ingest_local_viki_mock_payload()`
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ redacted audit output

This current path remains local-only, synthetic-data-only, and no-network.

## 3. Future controlled transport boundary

Future controlled transport boundary:

V.I.K.I. live middleware
→ RSA-compatible payload
→ transport authentication layer
→ message integrity verification
→ replay protection check
→ VERITAS live ingestion boundary
→ schema validation
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ redacted audit entry
→ commit gate

- VERITAS must treat every payload as untrusted until transport, integrity, replay, and schema validation pass.
- Transport success does not imply payload validity.
- Payload validity does not imply final commit approval.
- `SAFE_PROCEED` does not equal final commit approval.
- VERITAS commit gate remains authoritative.
- Timeout, failed authentication, failed integrity verification, replay suspicion, malformed payload, or missing payload must fail closed.

## 4. Proposed controlled transport assumptions

Initial controlled live transport should be:

- staging-only
- synthetic-data-only
- default-off
- feature-flag gated
- no production endpoint
- no public unauthenticated endpoint
- no real KYC data
- no live customer data
- no raw LLM text
- no raw V.I.K.I. reasoning

Transport assumptions:

- HTTPS is required.
- TLS 1.2 or TLS 1.3 should be required.
- mTLS is preferred for controlled service-to-service authentication where feasible.
- If mTLS is not available, signed requests using a secret stored outside the repository may be used for controlled testing.
- Secrets must never be committed to the repository.
- Endpoint URLs must not be added to public docs unless explicitly safe.
- Any future endpoint must be staging-only until separate production readiness review.

## 5. Authentication design

Two acceptable future authentication options:

### Option A: mTLS preferred

- V.I.K.I. and VERITAS authenticate each other using certificates.
- Certificates are provisioned outside the repository.
- Certificate rotation is required before production consideration.
- Certificate subject / SAN allowlisting should be defined before implementation.
- Failed certificate validation must fail closed.

### Option B: signed request fallback

- Request is signed by V.I.K.I. using a secret or private key stored outside the repository.
- VERITAS verifies the signature before schema validation.
- Key id must be included in metadata or headers.
- Secret rotation must be designed before implementation.
- Failed signature verification must fail closed.

- This design does not choose a production authentication mechanism.
- The initial controlled implementation must document which option is used.
- Authentication bypass is not permitted.
- Missing authentication must fail closed.

## 6. Draft transport metadata

Draft metadata that future transport may use:

- `X-VERITAS-Schema-Version`
- `X-VERITAS-Request-Id`
- `X-VERITAS-Correlation-Id`
- `X-VERITAS-Payload-Issued-At`
- `X-VERITAS-Signature`
- `X-VERITAS-Key-Id`
- `X-VERITAS-Body-SHA256`
- `X-VERITAS-Source-Environment`
- `X-VERITAS-Source-Instance-Id`

- Header names are draft names only.
- Final names must be reviewed before implementation.
- Headers must not contain PII, raw reasoning, secrets, tokens, or regulated data.
- `request_id` and `correlation_id` must match the payload where applicable.
- Signature or integrity checks must cover the body and relevant metadata.

## 7. Message integrity design

Future controlled live transport must provide message integrity.

Minimum integrity requirements:

- Verify payload body hash.
- Verify signature or mTLS identity.
- Verify `request_id`.
- Verify `correlation_id`.
- Verify timestamp / `payload_issued_at`.
- Verify `schema_version`.
- Reject tampered payloads.
- Reject modified `rsa_status`.
- Reject modified `trigger_source`.
- Reject body/header mismatch.

For signed request designs, signature should cover:

- HTTP method or transport operation name
- request path or operation target
- timestamp or `payload_issued_at`
- `request_id`
- `correlation_id`
- body hash
- `schema_version`

- Exact canonicalization rules must be defined before implementation.
- If canonicalization is ambiguous, implementation must not proceed.
- Failed integrity verification must fail closed.

## 8. Replay protection design

Replay protection must be designed before live implementation.

Minimum replay protection expectations:

- `request_id` must be unique within a defined replay window.
- `payload_issued_at` must be within accepted clock skew.
- Duplicate `request_id` within replay window must fail closed.
- Stale payloads must fail closed.
- Future timestamps beyond allowed skew must fail closed.
- Replay cache storage must be defined before implementation.
- Replay cache TTL must be defined before implementation.
- Replay cache failure should fail closed unless a separate reviewed degradation policy exists.

Reference existing local mock rule:

- local mock threshold: skew > 300 seconds fails closed
- skew = 300 seconds is accepted

- Controlled live integration may adopt the same skew threshold unless changed by separate reviewed design.
- Replay protection is mandatory before any real live transport.

## 9. Timeout and availability design

- V.I.K.I. timeout must fail closed.
- V.I.K.I. unreachable must fail closed.
- Connection refused must fail closed.
- Partial response must fail closed.
- Delayed response beyond threshold must fail closed.
- Missing payload must fail closed.
- Transport error must fail closed.

Expected generic behavior:

- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`
- `required_next_action`: `REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE`

- VERITAS must never infer `SAFE_PROCEED` from timeout or unavailability.
- Availability failure must not become normal approval.
- Retry behavior must be bounded and reviewed before implementation.

## 10. Payload schema relationship

This transport design depends on the controlled live payload schema draft.

Required payload fields remain:

- `schema_version`
- `rsa_status`
- `trigger_source`
- `timestamp`
- `request_id`
- `correlation_id`
- `payload_issued_at`

- Transport metadata must align with payload fields.
- Schema validation still runs after transport validation.
- Transport authentication does not replace schema validation.
- Schema validation does not replace transport authentication.
- Both are required before payload is accepted.

## 11. Redaction and logging policy

Future transport logs may include:

- `request_id`
- `correlation_id`
- `schema_version`
- `source_environment`
- `source_instance_id` when non-sensitive
- authentication result class
- integrity result class
- replay result class
- timeout result class
- VERITAS `continuation_decision`
- VERITAS `sandbox_commit_state`

Future transport logs must not include:

- secrets
- credentials
- access tokens
- refresh tokens
- private keys
- webhook secrets
- raw V.I.K.I. reasoning
- raw LLM text
- chain-of-thought
- hidden model state
- raw KYC records
- customer PII
- unredacted regulated data
- full signed secret material
- raw Authorization header

- Logging must be deterministic and redacted.
- Observability must not become a data leakage channel.
- Failed authentication logs must not expose secret material.

## 12. Credential and secret handling

- Secrets must not be stored in the repository.
- Secrets must not be stored in fixtures.
- Secrets must not be printed in logs.
- Secrets must not appear in docs.
- Secrets must not be passed through raw payload fields.
- Future implementation must use a secret manager or platform-provided secret storage.
- Rotation plan must be documented before production consideration.
- Revocation plan must be documented before production consideration.
- Test credentials, if ever used, must be synthetic and scoped to staging only.

## 13. Environment separation

Controlled live integration must separate:

- local
- CI
- staging
- controlled-test
- production

Rules:

- local mock receiver remains local-only and test-only.
- controlled live transport must be staging-only at first.
- production must not be enabled by this design.
- `source_environment` must not be used as an authorization mechanism.
- feature flags must be default-off.
- production deployment requires separate production readiness review.

## 14. Fail-closed matrix

| Failure class | Example | Expected behavior |
| --- | --- | --- |
| Missing authentication | Missing certificate or missing signature metadata | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Failed authentication | mTLS certificate rejected | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Failed signature verification | Signature mismatch for payload body | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Body hash mismatch | `X-VERITAS-Body-SHA256` differs from payload body hash | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Replay detected | Previously seen signed payload replayed | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Duplicate request_id | Same `request_id` appears within replay window | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Stale timestamp | `payload_issued_at` older than accepted replay window | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Future timestamp beyond skew | `payload_issued_at` too far ahead of receiver clock | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Timeout | Upstream request exceeds configured timeout | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| V.I.K.I. unreachable | DNS/network/connectivity failure | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Malformed payload | Invalid JSON or missing required fields | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Unknown rsa_status | `rsa_status` value not in accepted contract | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Forbidden raw reasoning field | Payload includes raw reasoning field | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Secret detected in payload | Payload contains secret-like token or key material | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Raw KYC data detected | Payload includes unredacted regulated KYC record | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |

## 15. Required implementation gates

Checklist before any transport implementation:

- threat model merged
- payload schema draft merged
- transport/auth design merged
- authentication option selected
- message integrity design finalized
- replay protection design finalized
- timeout policy finalized
- redaction/logging policy finalized
- secret storage approach approved
- staging-only feature flag defined
- synthetic-data-only test plan drafted
- rollback plan documented
- security review completed

## 16. Non-goals

This design does not permit:

- production live V.I.K.I. integration
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

## 17. Compatibility preservation

- `rsa_status` remains the v1 payload field.
- `RSASandboxPayload` remains the downstream payload container.
- `evaluate_rsa_sandbox_signal()` remains the downstream evaluator.
- `upstream_signal_source` remains `"RSA"`.
- `viki_status` is not introduced in this phase.
- `VIKIPayload` is not introduced in this phase.
- Any naming migration must be handled separately as v2.

## 18. What this design validates

- transport risks are documented before implementation
- authentication options are defined
- message integrity is required
- replay protection is required
- timeout must fail closed
- secrets must remain outside the repository
- logs must be redacted
- schema validation remains required
- no live implementation is introduced

## 19. What this design does not validate

- it does not implement transport
- it does not implement authentication
- it does not implement authorization
- it does not implement replay protection
- it does not validate production AML/KYC compliance
- it does not validate regulatory approval
- it does not provide legal advice
- it does not authorize production deployment
- it does not make VERITAS production-ready for live V.I.K.I.

## 20. Recommended next PR after this design

The next safe PR should be one of:

- replay protection and correlation-id design
- redaction and observability design
- live payload schema fixture examples
- controlled live failure-mode test plan
- controlled live integration implementation plan

The safest next PR is replay protection and correlation-id design, still documentation-only, because transport authentication must be paired with replay protection before any runtime implementation.
