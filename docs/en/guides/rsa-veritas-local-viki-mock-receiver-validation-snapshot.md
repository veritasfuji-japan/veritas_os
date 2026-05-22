# RSA ↔ VERITAS Local V.I.K.I. Mock Receiver Validation Snapshot

## 1. Purpose

This snapshot documents the current implemented validation state of the VERITAS-side local V.I.K.I. mock receiver.

- This is documentation-only.
- This is not a new implementation.
- This is not a live V.I.K.I. integration.
- This is not a production endpoint.
- This records the implemented local mock receiver behavior after the first test-only implementation was merged.

## 2. Implemented receiver surface

Implemented module:

- `veritas_os/governance/local_viki_mock_receiver.py`

Implemented helpers:

- `ingest_local_viki_mock_payload(raw_payload, *, receiver_now=None)`
- `build_local_viki_mock_unreachable_decision(*, receiver_now=None)`

The receiver accepts:

- JSON string payloads
- Mapping / dict-like payloads

The receiver does not:

- open a socket
- run an HTTP server
- call a network service
- connect to live V.I.K.I.
- consume live LLM text
- process real KYC data

## 3. Test-only guard validation

Explicit guard:

- `VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE=1`

Truthy values:

- `"1"`
- `"true"`
- `"yes"`
- `"on"`

Expected behavior:

- If the guard is missing or false, receiver helpers must raise before processing payload content.
- The guard prevents accidental use outside explicit local mock test contexts.
- The guard is not a production authorization system.
- The guard does not make the receiver production-safe.

## 4. Positive fixture validation

| Fixture ID | rsa_status | Expected continuation_decision | Expected reason_code | Expected sandbox_commit_state | Validation result |
| --- | --- | --- | --- | --- | --- |
| VIKI_POS_001 | SAFE_PROCEED | CONTINUE_TO_BIND_BOUNDARY | UPSTREAM_SAFE_PROCEED_SIGNAL | SUSPENDED_NOT_COMMITTED | Implemented |
| VIKI_POS_002 | DENSITY_THROTTLED | CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED | UPSTREAM_INTERVENTION_DENSITY_THROTTLE | SUSPENDED_NOT_COMMITTED | Implemented |
| VIKI_POS_003 | ALGORITHMIC_HUMILITY_ENGAGED | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_INCOMPLETE_KYC_CONTEXT | SUSPENDED_NOT_COMMITTED | Implemented |
| VIKI_POS_004 | DEFERRAL_ENGAGED | BLOCK_FINAL_COMMIT | UPSTREAM_CRITICAL_DEFERRAL_SIGNAL | BLOCKED_NOT_COMMITTED | Implemented |

## 5. Negative schema validation

Invalid local mock payloads must fail closed.

| Fixture class | Example | Expected reason_code | Expected continuation_decision | Validation result |
| --- | --- | --- | --- | --- |
| Invalid JSON / malformed JSON | Non-parseable JSON string | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Missing rsa_status | `rsa_status` key absent | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Missing trigger_source | `trigger_source` key absent | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Missing timestamp | `timestamp` key absent | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Null required field | Required key set to `null` | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Empty trigger_source | `trigger_source` is empty string | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Unknown rsa_status | Unsupported `rsa_status` value | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Invalid timestamp | Non-ISO or non-parseable timestamp | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Payload shape mismatch | Non-mapping or malformed structure | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Optional original_llm_intent present but invalid | Unsupported type for `original_llm_intent` | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Optional rsa_action_taken present but invalid | Unsupported type for `rsa_action_taken` | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |

## 6. Clock skew validation

Implemented clock skew rule:

- threshold is exclusive
- skew > 300 seconds fails closed
- skew = 300 seconds is accepted
- strict inequality must be used
- greater-than-or-equal must not be used

| Clock skew | Expected result |
| --- | --- |
| 299 seconds | accepted |
| 300 seconds | accepted |
| 301 seconds | fail closed |
| -301 seconds / future skew 301 seconds | fail closed |

Failed clock skew validation maps to:

- `reason_code`: `UPSTREAM_MOCK_PAYLOAD_INVALID`
- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`

## 7. Unreachable mock generator validation

`build_local_viki_mock_unreachable_decision()` returns a deterministic fail-closed output for unavailable local mock generator cases.

Expected output:

- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `reason_code`: `UPSTREAM_MIDDLEWARE_OFFLINE`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`
- `required_next_action`: `REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE`

- timeout / unreachable must never be converted into `SAFE_PROCEED`
- no payload must never be inferred as valid payload
- unavailable local mock generator means VERITAS fails closed

## 8. Audit redaction validation

Audit output redacts raw upstream fields by default.

Expected default audit behavior:

- `original_llm_intent`: `[REDACTED]`
- `rsa_action_taken`: `[REDACTED]`

- raw upstream reasoning is not accepted
- V.I.K.I. internal reasoning is not stored
- chain-of-thought is not stored
- hidden model state is not stored

Audit preserves deterministic fields:

- `upstream_signal_source`
- `rsa_status`
- `trigger_source`
- `timestamp`
- `veritas_continuation_decision`
- `veritas_sandbox_commit_state`

## 9. Fail-closed output shape

Invalid payload fail-closed shape:

```json
{
  "veritas_decision": {
    "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
    "reason_code": "UPSTREAM_MOCK_PAYLOAD_INVALID",
    "authority_evidence_status": "INSUFFICIENT",
    "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
    "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
    "required_next_action": "REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW"
  },
  "audit_entry": {
    "upstream_signal_source": "RSA",
    "rsa_status": "INVALID_OR_UNAVAILABLE",
    "trigger_source": "LOCAL_VIKI_MOCK_RECEIVER",
    "original_llm_intent": "[REDACTED]",
    "rsa_action_taken": "[REDACTED]",
    "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
    "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED"
  }
}
```
