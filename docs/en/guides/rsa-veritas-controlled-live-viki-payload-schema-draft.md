# RSA ↔ VERITAS Controlled Live V.I.K.I. Payload Schema Draft

## 1. Purpose

This document defines the **draft payload schema** for a future controlled live V.I.K.I. integration.

- This is documentation-only.
- This is not a live integration.
- This is not a runtime implementation.
- This is not a production API endpoint.
- This does not authorize production use.
- This does not process real KYC data.
- This does not provide legal or regulatory approval.
- This schema draft must be reviewed before any transport, endpoint, or live middleware work begins.

## 2. Current baseline

Current validated local mock path:

static synthetic JSON fixture
→ `ingest_local_viki_mock_payload()`
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ redacted audit output

The controlled live integration threat model has been merged, and this schema draft follows that threat model.

Current v1 compatibility contract remains:

- `rsa_status`
- `RSASandboxPayload`
- `evaluate_rsa_sandbox_signal()`
- `upstream_signal_source = "RSA"`

## 3. Future live payload boundary

Future live payload boundary:

V.I.K.I. live middleware
→ RSA-compatible live payload
→ controlled transport boundary
→ VERITAS live ingestion boundary
→ schema validation
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ audit entry
→ commit gate

- VERITAS treats every live payload as untrusted until schema validation passes.
- VERITAS consumes only the emitted RSA-compatible payload.
- VERITAS does not consume V.I.K.I. internal reasoning.
- VERITAS does not execute hidden V.I.K.I. logic.
- VERITAS does not infer `SAFE_PROCEED` from missing, malformed, delayed, or unavailable payloads.

## 4. Draft payload object

The payload is a single JSON object.

Required fields:

- `schema_version`
- `rsa_status`
- `trigger_source`
- `timestamp`
- `request_id`
- `correlation_id`
- `payload_issued_at`

Optional accepted fields:

- `source_environment`
- `source_instance_id`
- `rsa_action_taken`
- `original_llm_intent`
- `upstream_confidence_class`
- `upstream_latency_ms`
- `upstream_reason_code`

Explicitly forbidden fields:

- `chain_of_thought`
- `hidden_model_state`
- `raw_llm_reasoning`
- `raw_viki_reasoning`
- `raw_kyc_record`
- `customer_pii`
- `secrets`
- `credentials`
- `api_key`
- `access_token`
- `refresh_token`
- `private_key`
- `webhook_secret`
- `unredacted_regulated_data`

- Optional raw-intent/action fields must be redacted by default in audit output.
- Forbidden fields must be rejected or stripped before audit persistence.
- The presence of chain-of-thought or hidden model state must fail closed.

## 5. Required field definitions

| Field | Type | Required | Description | Validation rule |
| --- | --- | --- | --- | --- |
| `schema_version` | string | yes | Draft schema version for controlled live payloads. | Must equal `"v1alpha1"` for this draft. |
| `rsa_status` | string | yes | RSA-compatible upstream status. | Must be one of `SAFE_PROCEED`, `DENSITY_THROTTLED`, `ALGORITHMIC_HUMILITY_ENGAGED`, `DEFERRAL_ENGAGED`. |
| `trigger_source` | string | yes | Deterministic source label for why the upstream status was emitted. | Must be non-empty and must not contain raw reasoning or PII. |
| `timestamp` | string | yes | Primary event timestamp. | Must be RFC 3339 UTC or timezone-aware ISO-8601 normalized to UTC. |
| `request_id` | string | yes | Unique identifier for the upstream request. | Must be non-empty. Future implementation should enforce uniqueness within replay window. |
| `correlation_id` | string | yes | Identifier used to correlate V.I.K.I. emission, VERITAS ingestion, audit entry, and review event. | Must be non-empty and must not contain PII. |
| `payload_issued_at` | string | yes | Timestamp when V.I.K.I. emitted the payload. | Must be RFC 3339 UTC or timezone-aware ISO-8601 normalized to UTC. |

## 6. Optional field definitions

| Field | Type | Required | Description | Validation / audit rule |
| --- | --- | --- | --- | --- |
| `source_environment` | string | no | Environment label such as local, staging, controlled-test. | Must not be used to enable production behavior. |
| `source_instance_id` | string | no | Non-secret identifier for V.I.K.I. instance. | Must not contain secrets, host credentials, or PII. |
| `rsa_action_taken` | string | no | Short upstream action label. | Allowed only as non-empty string. Redacted by default in audit output. |
| `original_llm_intent` | string | no | Short upstream intent label. | Allowed only as non-empty string. Redacted by default in audit output. |
| `upstream_confidence_class` | string | no | Coarse confidence class, not raw probability trace. | Allowed values should be `LOW`, `MEDIUM`, `HIGH`, or `UNSPECIFIED`. |
| `upstream_latency_ms` | integer | no | Measured upstream processing latency in milliseconds. | Must be non-negative integer if present. |
| `upstream_reason_code` | string | no | Deterministic upstream reason code. | Must not contain raw reasoning, PII, or regulated data. |

## 7. Accepted rsa_status values

`SAFE_PROCEED`:

- May continue toward normal bind-boundary evaluation.
- Does not equal final commit approval.
- VERITAS commit gate remains authoritative.

`DENSITY_THROTTLED`:

- Indicates upstream intervention was applied.
- VERITAS may continue with upstream intervention logged.

`ALGORITHMIC_HUMILITY_ENGAGED`:

- Indicates incomplete or uncertain upstream context.
- VERITAS should pause for human review.

`DEFERRAL_ENGAGED`:

- Indicates critical upstream deferral.
- VERITAS should block final commit.

- Unknown `rsa_status` must fail closed.
- Empty `rsa_status` must fail closed.
- Null `rsa_status` must fail closed.
- Any attempt to encode multiple statuses must fail closed.

## 8. Timestamp and replay requirements

- `timestamp` and `payload_issued_at` must be RFC 3339 UTC or timezone-aware ISO-8601 normalized to UTC.
- Naive timestamps are rejected.
- Invalid timestamp strings are rejected.
- Clock skew threshold must be explicitly defined before implementation.
- Existing local mock threshold is skew > 300 seconds fails closed and skew = 300 seconds accepted.
- Live integration may adopt the same threshold unless changed by a separate reviewed design.
- Replay protection must be designed before live implementation.
- `request_id` and `correlation_id` are placeholders for replay protection and traceability.
- Duplicate `request_id` within the replay window should fail closed in future implementation.

## 9. Example valid payloads

Example `SAFE_PROCEED`:

```json
{
  "schema_version": "v1alpha1",
  "rsa_status": "SAFE_PROCEED",
  "trigger_source": "SRC_Normal_State",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "request_id": "req_viki_000001",
  "correlation_id": "corr_viki_veritas_000001",
  "payload_issued_at": "2026-05-20T23:01:35.876Z",
  "source_environment": "controlled-test",
  "source_instance_id": "viki-local-controlled-001",
  "rsa_action_taken": "No_Upstream_Intervention_Required",
  "original_llm_intent": "Continue_To_Normal_Bind_Boundary_Evaluation",
  "upstream_confidence_class": "HIGH",
  "upstream_latency_ms": 87,
  "upstream_reason_code": "UPSTREAM_NORMAL_STATE"
}
```

Example `ALGORITHMIC_HUMILITY_ENGAGED`:

```json
{
  "schema_version": "v1alpha1",
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "request_id": "req_viki_000002",
  "correlation_id": "corr_viki_veritas_000002",
  "payload_issued_at": "2026-05-20T23:01:35.876Z",
  "source_environment": "controlled-test",
  "source_instance_id": "viki-local-controlled-001",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "upstream_confidence_class": "LOW",
  "upstream_latency_ms": 112,
  "upstream_reason_code": "UPSTREAM_INCOMPLETE_CONTEXT"
}
```

## 10. Example invalid payloads

Invalid unknown status:

```json
{
  "schema_version": "v1alpha1",
  "rsa_status": "UNKNOWN_STATE",
  "trigger_source": "SRC_Unknown_State",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "request_id": "req_viki_invalid_001",
  "correlation_id": "corr_viki_veritas_invalid_001",
  "payload_issued_at": "2026-05-20T23:01:35.876Z"
}
```

Expected behavior:

- fail closed
- `continuation_decision: PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state: SUSPENDED_NOT_COMMITTED`
- do not infer `SAFE_PROCEED`

Invalid raw reasoning:

```json
{
  "schema_version": "v1alpha1",
  "rsa_status": "SAFE_PROCEED",
  "trigger_source": "SRC_Normal_State",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "request_id": "req_viki_invalid_002",
  "correlation_id": "corr_viki_veritas_invalid_002",
  "payload_issued_at": "2026-05-20T23:01:35.876Z",
  "chain_of_thought": "FORBIDDEN"
}
```

Expected behavior:

- fail closed or reject before audit persistence
- never store chain-of-thought
- never store hidden model state
- never store raw upstream reasoning

## 11. Schema validation failure behavior

The following must fail closed:

- invalid JSON
- payload is not a JSON object
- missing `schema_version`
- unsupported `schema_version`
- missing `rsa_status`
- null `rsa_status`
- unknown `rsa_status`
- missing `trigger_source`
- empty `trigger_source`
- missing `timestamp`
- invalid `timestamp`
- naive `timestamp`
- missing `request_id`
- missing `correlation_id`
- duplicate `request_id` within replay window in future implementation
- missing `payload_issued_at`
- forbidden raw reasoning fields
- forbidden secret or credential fields
- raw KYC or regulated data fields
- payload shape mismatch
- field type mismatch

Expected generic behavior:

- `continuation_decision: PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state: SUSPENDED_NOT_COMMITTED`
- `required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE` or `REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW` depending on failure class

## 12. Redaction and audit behavior

Audit entries may preserve:

- `upstream_signal_source`
- `schema_version`
- `rsa_status`
- `trigger_source`
- `timestamp`
- `request_id`
- `correlation_id`
- `payload_issued_at`
- `source_environment`
- `source_instance_id` when non-sensitive
- `upstream_latency_ms`
- `upstream_reason_code`
- VERITAS `continuation_decision`
- VERITAS `reason_code`
- VERITAS `sandbox_commit_state`

Audit entries must redact or reject:

- `original_llm_intent`
- `rsa_action_taken`
- chain-of-thought
- hidden model state
- raw V.I.K.I. reasoning
- raw LLM text
- raw KYC records
- customer PII
- secrets
- credentials
- tokens
- private keys
- unredacted regulated data

## 13. Transport assumptions

- This schema draft does not define transport implementation.
- Future transport must define authentication.
- Future transport must define message integrity.
- Future transport must define replay protection.
- Future transport must define timeout behavior.
- Future transport must define observability without sensitive payload logging.
- This document does not add an endpoint or network call.

## 14. Compatibility preservation

- `rsa_status` remains the v1 payload field.
- `RSASandboxPayload` remains the downstream payload container.
- `evaluate_rsa_sandbox_signal()` remains the downstream evaluator.
- `upstream_signal_source` remains `"RSA"`.
- `viki_status` is not introduced in this phase.
- `VIKIPayload` is not introduced in this phase.
- Any naming migration must be handled separately as v2.

## 15. Non-goals

This schema draft does not permit:

- production live V.I.K.I. integration
- production API endpoint
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- final commit automation based only on V.I.K.I.
- bypass of VERITAS commit gate
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 16. Approval gates before implementation

Checklist before any live payload implementation:

- [ ] threat model merged
- [ ] schema draft merged
- [ ] schema reviewed by human reviewer
- [ ] transport/auth design merged
- [ ] replay protection design merged
- [ ] redaction policy reviewed
- [ ] failure-mode test plan drafted
- [ ] staging-only plan drafted
- [ ] synthetic-data-only plan drafted
- [ ] rollback plan documented
- [ ] security review completed

## 17. What this schema draft validates

- required live payload fields are defined
- optional live payload fields are constrained
- forbidden fields are explicitly listed
- accepted `rsa_status` values are fixed
- timestamp and replay expectations are documented
- audit redaction expectations are documented
- compatibility with `RSASandboxPayload` is preserved
- no live implementation is introduced

## 18. What this schema draft does not validate

- it does not implement live V.I.K.I.
- it does not validate transport
- it does not validate authentication
- it does not validate authorization
- it does not validate replay protection
- it does not validate production AML/KYC compliance
- it does not validate regulatory approval
- it does not provide legal advice
- it does not authorize production deployment

## 19. Recommended next PR after this schema draft

The next safe PR after this schema draft should be one of:

- controlled transport/authentication design
- replay protection and correlation-id design
- redaction and observability design
- live payload schema fixture examples
- controlled live integration implementation plan

Recommended:

The safest next PR is controlled transport/authentication design, still documentation-only, because the schema contract should be followed by a secure transport boundary before any runtime implementation.
