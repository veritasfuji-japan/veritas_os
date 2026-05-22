# RSA ↔ VERITAS Local V.I.K.I. Mock Receiver Test Fixture Plan

## 1. Purpose

This document defines the fixture plan for future tests of the VERITAS-side local V.I.K.I. mock ingestion receiver.

- This is not a runtime implementation.
- This is not a test implementation.
- This is not a live V.I.K.I. connection.
- This is not a production API endpoint.
- This is a documentation-only fixture plan.
- The goal is to define expected test coverage before implementing the local mock receiver.

## 2. Current baseline

The current merged baseline includes:

- Static sandbox documentation.
- Four dedicated per-variant validation snapshots.
- Static fixture matrix.
- Sandbox reviewer index.
- Live V.I.K.I. integration design note.
- Live V.I.K.I. integration reviewer checklist.
- Local V.I.K.I. mock ingestion receiver design.

This fixture plan follows the local mock ingestion receiver design and remains local-only and synthetic-data-only.

## 3. Test boundary model

- V.I.K.I. mock generator emits synthetic RSA-compatible payloads.
- VERITAS treats all incoming payloads as untrusted until schema validation passes.
- VERITAS maps accepted payloads through RSASandboxPayload and evaluate_rsa_sandbox_signal().
- VERITAS must fail closed on malformed, missing, unknown, invalid, delayed, or unreachable upstream payloads.
- VERITAS audit output must redact raw upstream intent/action fields by default.
- No live V.I.K.I. internal reasoning is ingested.

## 4. Positive fixture matrix

| Fixture ID | Mock scenario | rsa_status | Expected continuation_decision | Expected reason_code | Expected sandbox_commit_state |
| --- | --- | --- | --- | --- | --- |
| VIKI_POS_001 | Normal State | SAFE_PROCEED | CONTINUE_TO_BIND_BOUNDARY | UPSTREAM_SAFE_PROCEED_SIGNAL | SUSPENDED_NOT_COMMITTED |
| VIKI_POS_002 | Entropy Spike | DENSITY_THROTTLED | CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED | UPSTREAM_INTERVENTION_DENSITY_THROTTLE | SUSPENDED_NOT_COMMITTED |
| VIKI_POS_003 | Incomplete KYC Data | ALGORITHMIC_HUMILITY_ENGAGED | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_INCOMPLETE_KYC_CONTEXT | SUSPENDED_NOT_COMMITTED |
| VIKI_POS_004 | Severe Context Decay | DEFERRAL_ENGAGED | BLOCK_FINAL_COMMIT | UPSTREAM_CRITICAL_DEFERRAL_SIGNAL | BLOCKED_NOT_COMMITTED |

## 5. Positive fixture payload examples

SAFE_PROCEED:

```json
{
  "rsa_status": "SAFE_PROCEED",
  "trigger_source": "SRC_Normal_State",
  "original_llm_intent": "Continue_To_Normal_Bind_Boundary_Evaluation",
  "rsa_action_taken": "No_Upstream_Intervention_Required",
  "timestamp": "2026-05-20T23:01:35.876Z"
}
```

DENSITY_THROTTLED:

```json
{
  "rsa_status": "DENSITY_THROTTLED",
  "trigger_source": "SEI_Entropy_Spike",
  "original_llm_intent": "Generate_High_Density_Operational_Response",
  "rsa_action_taken": "Output_Density_Throttled_Before_Emission",
  "timestamp": "2026-05-20T23:01:35.876Z"
}
```

ALGORITHMIC_HUMILITY_ENGAGED:

```json
{
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-05-20T23:01:35.876Z"
}
```

DEFERRAL_ENGAGED:

```json
{
  "rsa_status": "DEFERRAL_ENGAGED",
  "trigger_source": "SRC_Severe_Context_Decay",
  "original_llm_intent": "Proceed_To_Final_Commit",
  "rsa_action_taken": "Final_Commit_Deferred_Due_To_Context_Decay",
  "timestamp": "2026-05-20T23:01:35.876Z"
}
```

Future tests may generate dynamic timestamps, but fixture examples should remain deterministic in documentation.

## 6. Negative schema fixture matrix

| Fixture ID | Invalid condition | Example failure | Expected VERITAS behavior | Expected reason_code |
| --- | --- | --- | --- | --- |
| VIKI_NEG_001 | Invalid JSON | payload cannot be parsed as JSON | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_002 | Missing rsa_status | required field omitted | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_003 | Missing trigger_source | required field omitted | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_004 | Missing timestamp | required field omitted | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_005 | Null required field | rsa_status is null | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_006 | Empty trigger_source | trigger_source is empty string | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_007 | Unknown rsa_status | rsa_status = "UNKNOWN_STATE" | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_008 | Invalid timestamp format | timestamp is not RFC 3339 UTC | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_009 | Clock skew too large | timestamp differs from receiver clock by more than 300 seconds | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_010 | Payload shape mismatch | payload is array or nested wrapper instead of expected object | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |

## 7. Timeout and unreachable fixture matrix

| Fixture ID | Condition | Expected continuation_decision | Expected reason_code | Expected sandbox_commit_state | Expected next action |
| --- | --- | --- | --- | --- | --- |
| VIKI_TIMEOUT_001 | No payload received before timeout | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MIDDLEWARE_OFFLINE | SUSPENDED_NOT_COMMITTED | REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE |
| VIKI_TIMEOUT_002 | Local mock generator unreachable | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MIDDLEWARE_OFFLINE | SUSPENDED_NOT_COMMITTED | REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE |
| VIKI_TIMEOUT_003 | Connection refused | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MIDDLEWARE_OFFLINE | SUSPENDED_NOT_COMMITTED | REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE |

Timeout or unreachable conditions must never be converted into SAFE_PROCEED.
Only a schema-valid SAFE_PROCEED payload may continue toward normal bind-boundary evaluation.

## 8. Audit redaction fixture matrix

| Fixture ID | Input field | Expected audit behavior |
| --- | --- | --- |
| VIKI_AUDIT_001 | original_llm_intent | redacted by default |
| VIKI_AUDIT_002 | rsa_action_taken | redacted by default |
| VIKI_AUDIT_003 | raw upstream reasoning | not accepted / not stored |
| VIKI_AUDIT_004 | V.I.K.I. internal reasoning | not accepted / not stored |
| VIKI_AUDIT_005 | chain-of-thought | not accepted / not stored |
| VIKI_AUDIT_006 | hidden model state | not accepted / not stored |

Audit entries should preserve deterministic fields:

- rsa_status
- trigger_source
- timestamp
- VERITAS continuation_decision
- VERITAS reason_code
- VERITAS sandbox_commit_state

## 9. Expected fail-closed output shape

Expected generic fail-closed output shape for invalid local mock payloads:

```json
{
  "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
  "reason_code": "UPSTREAM_MOCK_PAYLOAD_INVALID",
  "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW"
}
```

Expected generic fail-closed output shape for timeout or unreachable local mock generator:

```json
{
  "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
  "reason_code": "UPSTREAM_MIDDLEWARE_OFFLINE",
  "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE"
}
```

- These reason_code values are reserved identifiers.
- Formal definitions should be added to core/errors.py when the local mock receiver is implemented.
- Do not treat these strings as stable constants until that implementation PR is merged.

## 10. Compatibility contract

The v1 compatibility contract remains unchanged:

- rsa_status
- RSASandboxPayload
- evaluate_rsa_sandbox_signal()
- upstream_signal_source = "RSA"

- Do not rename rsa_status to viki_status in this phase.
- Do not rename RSASandboxPayload to VIKIPayload in this phase.
- Any naming migration must be handled separately as a v2 migration.

## 11. What this fixture plan validates

- The intended positive and negative fixture coverage is documented before implementation.
- The four established mock scenarios have expected VERITAS decisions.
- Invalid schema cases are expected to fail closed.
- Timeout and unreachable cases are expected to fail closed.
- Audit redaction expectations are documented.
- The next implementation PR can be scoped to local-only and synthetic-data-only behavior.

## 12. What this fixture plan does not validate

- It does not implement tests.
- It does not implement the receiver.
- It does not add an API endpoint.
- It does not connect live V.I.K.I. middleware.
- It does not validate live V.I.K.I. internal reasoning.
- It does not validate network transport.
- It does not validate authentication or authorization.
- It does not process live LLM text.
- It does not process real KYC data.
- It does not implement production AML/KYC compliance.
- It does not provide regulatory approval.
- It does not provide legal advice.
- It does not change production runtime governance.

## 13. Recommended next PR after this fixture plan

After this fixture plan is merged, the next safe PR should be local mock receiver implementation behind an explicit test-only guard.

The implementation should:

- be local-only
- be synthetic-data-only
- avoid production endpoints
- avoid network secrets
- avoid live V.I.K.I. integration
- include tests based on this fixture plan
